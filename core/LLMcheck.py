import json
import numpy as np
from typing import List, Dict, Tuple
from neo4j import GraphDatabase
from openai import AzureOpenAI
import tkinter as tk
from tkinter import messagebox
import re

# 兼容打包和開發環境的導入
try:
    from core.prompt_templates import get_contract_analysis_prompt, get_keyword_extraction_prompt
    from core.project_type_selector import show_project_type_selector
except ModuleNotFoundError:
    from prompt_templates import get_contract_analysis_prompt, get_keyword_extraction_prompt
    from project_type_selector import show_project_type_selector


class JSONChecklistQuerySystem:
    def __init__(self, json_file_path, azure_endpoint, azure_api_key, neo4j_uri, neo4j_username, neo4j_password):

        with open(json_file_path, 'r', encoding='utf-8') as f:
            self.checklist_data = json.load(f)

        self.uri = neo4j_uri
        self.auth = (neo4j_username, neo4j_password)
        self.driver = GraphDatabase.driver(self.uri, auth=self.auth)

        self.llm_client = AzureOpenAI(
            azure_endpoint=azure_endpoint,
            api_key=azure_api_key,
            api_version="2025-01-01-preview"
        )

    def close(self):
        self.driver.close()

    def find_item_by_number(self, item_number):

        for main_item in self.checklist_data:
            if main_item["主項次"] == item_number:
                return {
                    "type": "main",
                    "data": main_item
                }

            for sub_item in main_item["子項目"]:
                if sub_item["項次"] == item_number:
                    return {
                        "type": "sub",
                        "data": sub_item
                    }

                if "子項目" in sub_item and sub_item["子項目"]:
                    for sub_sub_item in sub_item["子項目"]:
                        if sub_sub_item["項次"] == item_number:
                            return {
                                "type": "sub_sub",
                                "data": sub_sub_item
                            }
        return None

    def create_fulltext_index(self):
        """
        建立 Neo4j 全文索引以支援 BM25 搜尋

        注意：此方法應在上傳文件後執行一次
        如果索引已存在會跳過
        """
        with self.driver.session() as session:
            try:
                # 檢查索引是否已存在
                check_query = "SHOW INDEXES YIELD name WHERE name = 'clause_fulltext' RETURN count(*) as count"
                result = session.run(check_query)
                count = result.single()['count']

                if count > 0:
                    print("全文索引 'clause_fulltext' 已存在，跳過建立")
                    return True

                # 建立全文索引
                create_query = """
                CREATE FULLTEXT INDEX clause_fulltext IF NOT EXISTS
                FOR (c:Clause)
                ON EACH [c.title, c.content]
                OPTIONS {
                  indexConfig: {
                    `fulltext.analyzer`: 'standard',
                    `fulltext.eventually_consistent`: false
                  }
                }
                """
                session.run(create_query)
                print("✅ 成功建立全文索引 'clause_fulltext'")
                return True

            except Exception as e:
                print(f"建立全文索引時發生錯誤: {e}")
                print("將使用傳統 CONTAINS 搜尋作為備用方案")
                return False

    def bm25_search(self, keywords: List[str], top_k: int = 100) -> List[Dict]:
        """
        使用 Neo4j BM25 全文索引搜尋相關條款

        Args:
            keywords: 關鍵字列表
            top_k: 返回前 K 個結果

        Returns:
            依 BM25 分數排序的條款列表
        """
        if not keywords:
            return []

        # 將關鍵字組合成查詢字串
        # 使用 OR 連接，讓任一關鍵字匹配即可
        query_string = " OR ".join(keywords)

        with self.driver.session() as session:
            try:
                # 使用全文索引搜尋
                bm25_query = """
                CALL db.index.fulltext.queryNodes('clause_fulltext', $query_string)
                YIELD node, score
                WITH node as c, score
                MATCH (d:Document)-[:HAS_SECTION|HAS_CLAUSE*]->(c)
                RETURN c.number as number,
                       c.title as title,
                       c.content as content,
                       c.major_title as major_title,
                       score as bm25_score,
                       CASE
                         WHEN d.type = 'contract' THEN 'contract'
                         WHEN d.type = 'bidding_document' THEN
                           CASE
                             WHEN (c)<-[:HAS_CLAUSE]-(:Section {name: '補充投標須知'}) THEN 'supplement_notice'
                             ELSE 'bidding_notice'
                           END
                         WHEN d.type = 'appendix_a' THEN 'appendix_a'
                         ELSE 'unknown'
                       END as source
                ORDER BY score DESC
                LIMIT $top_k
                """

                result = session.run(bm25_query, query_string=query_string, top_k=top_k)

                clauses = []
                for record in result:
                    clauses.append({
                        'number': record['number'],
                        'title': record['title'],
                        'content': record['content'],
                        'major_title': record.get('major_title', ''),
                        'source': record['source'],
                        'bm25_score': float(record['bm25_score'])
                    })

                print(f"BM25 搜尋找到 {len(clauses)} 個條款（查詢: {query_string[:50]}...）")
                if clauses:
                    top_3_scores = [(c['number'], f"{c['bm25_score']:.3f}") for c in clauses[:3]]
                    print(f"Top 3 BM25 分數: {top_3_scores}")

                return clauses

            except Exception as e:
                error_msg = str(e)
                if 'clause_fulltext' in error_msg or 'index' in error_msg.lower():
                    print(f"⚠ BM25 搜尋失敗（索引可能不存在）: {error_msg}")
                    print("→ 自動回退到傳統 CONTAINS 搜尋")
                    return self.find_related_clauses(keywords)
                else:
                    print(f"BM25 搜尋錯誤: {e}")
                    return []

    def find_related_clauses(self, keywords):
        """在所有文件中搜尋相關條款"""
        with self.driver.session() as session:
            # 搜尋契約文件條款
            contract_query = """
            MATCH (d:Document {type: 'contract'})-[:HAS_CLAUSE]->(c:Clause)
            WHERE ANY(keyword IN $keywords WHERE
                toLower(c.title) CONTAINS toLower(keyword) OR
                toLower(c.content) CONTAINS toLower(keyword))
            RETURN c.number as number,
                   c.title as title,
                   c.content as content,
                   'contract' as source
            ORDER BY c.number
            """

            bidding_query = """
            MATCH (d:Document {type: 'bidding_document'})-[:HAS_SECTION]->(s:Section {name: '投標須知'})-[:HAS_CLAUSE]->(c:Clause)
            WHERE ANY(keyword IN $keywords WHERE
                toLower(c.title) CONTAINS toLower(keyword) OR
                toLower(c.content) CONTAINS toLower(keyword))
            RETURN c.number as number,
                   c.title as title,
                   c.content as content,
                   'bidding_notice' as source
            ORDER BY c.number
            """

            # 搜尋補充投標須知條款
            supplement_query = """
            MATCH (d:Document {type: 'bidding_document'})-[:HAS_SECTION]->(s:Section {name: '補充投標須知'})-[:HAS_CLAUSE]->(c:Clause)
            WHERE ANY(keyword IN $keywords WHERE
                toLower(c.title) CONTAINS toLower(keyword) OR
                toLower(c.content) CONTAINS toLower(keyword))
            RETURN c.number as number,
                   c.title as title,
                   c.content as content,
                   'supplement_notice' as source
            ORDER BY c.number
            """

            # 搜尋投標須知附錄A條款
            appendix_a_query = """
            MATCH (d:Document {type: 'appendix_a'})-[:HAS_SECTION]->(s:Section {name: '投標須知附錄A'})-[:HAS_CLAUSE]->(c:Clause)
            WHERE ANY(keyword IN $keywords WHERE
                toLower(c.title) CONTAINS toLower(keyword) OR
                toLower(c.content) CONTAINS toLower(keyword) OR
                toLower(c.major_title) CONTAINS toLower(keyword))
            RETURN c.number as number,
                   c.title as title,
                   c.content as content,
                   c.major_title as major_title,
                   'appendix_a' as source
            ORDER BY c.number
            """

            clauses = []

            # 執行四個查詢並合併結果
            contract_result = session.run(contract_query, keywords=keywords)
            for record in contract_result:
                clauses.append({
                    'number': record['number'],
                    'title': record['title'],
                    'content': record['content'],
                    'source': record['source']
                })

            bidding_result = session.run(bidding_query, keywords=keywords)
            for record in bidding_result:
                clauses.append({
                    'number': record['number'],
                    'title': record['title'],
                    'content': record['content'],
                    'source': record['source']
                })

            supplement_result = session.run(
                supplement_query, keywords=keywords)
            for record in supplement_result:
                clauses.append({
                    'number': record['number'],
                    'title': record['title'],
                    'content': record['content'],
                    'source': record['source']
                })

            # 添加附錄A搜尋結果
            appendix_a_result = session.run(appendix_a_query, keywords=keywords)
            for record in appendix_a_result:
                clauses.append({
                    'number': record['number'],
                    'title': record['title'],
                    'content': record['content'],
                    'major_title': record.get('major_title', ''),
                    'source': record['source']
                })

            return clauses

    def generate_embeddings(self, texts: List[str], model="text-embedding-3-small") -> List[List[float]]:
        """生成文本的embedding向量"""
        try:
            # Azure OpenAI embedding API
            embeddings = []
            
            # 分批處理避免API限制 (減少批量大小避免token超限)
            batch_size = 10
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                
                response = self.llm_client.embeddings.create(
                    model=model,
                    input=batch
                )
                
                batch_embeddings = [data.embedding for data in response.data]
                embeddings.extend(batch_embeddings)
                
                print(f"已處理 {min(i + batch_size, len(texts))}/{len(texts)} 個文本的embedding")
            
            return embeddings
            
        except Exception as e:
            print(f"生成embedding錯誤: {e}")
            return []

    def cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """計算兩個向量的餘弦相似度"""
        try:
            v1 = np.array(vec1)
            v2 = np.array(vec2)
            
            dot_product = np.dot(v1, v2)
            norm1 = np.linalg.norm(v1)
            norm2 = np.linalg.norm(v2)
            
            if norm1 == 0 or norm2 == 0:
                return 0.0
                
            return float(dot_product / (norm1 * norm2))
            
        except Exception as e:
            print(f"計算相似度錯誤: {e}")
            return 0.0

    def store_embeddings_in_neo4j(self):
        """為所有條款生成並儲存embedding"""
        print("開始為所有條款生成embedding...")
        
        with self.driver.session() as session:
            # 獲取所有條款
            all_clauses_query = """
            MATCH (c:Clause)
            WHERE c.embedding IS NULL
            RETURN c.number as number, 
                   c.title as title, 
                   c.content as content,
                   labels(c) as labels,
                   elementId(c) as element_id
            """
            
            result = session.run(all_clauses_query)
            clauses_data = []
            
            for record in result:
                # 截斷過長的文本避免embedding API限制 (大約保持在800個字符以內)
                title = record['title'][:200] if record['title'] else ""
                content = record['content'][:600] if record['content'] else ""
                clause_text = f"{title} {content}"
                
                clauses_data.append({
                    'element_id': record['element_id'],
                    'number': record['number'],
                    'text': clause_text
                })
            
            if not clauses_data:
                print("所有條款都已有embedding，跳過生成")
                return
                
            print(f"找到 {len(clauses_data)} 個需要生成embedding的條款")
            
            # 生成embedding
            texts = [clause['text'] for clause in clauses_data]
            embeddings = self.generate_embeddings(texts)
            
            if len(embeddings) != len(clauses_data):
                print(f"警告：embedding數量 {len(embeddings)} 與條款數量 {len(clauses_data)} 不符")
                return
            
            # 儲存embedding到Neo4j
            update_query = """
            MATCH (c:Clause)
            WHERE elementId(c) = $element_id
            SET c.embedding = $embedding
            """
            
            for clause_data, embedding in zip(clauses_data, embeddings):
                session.run(update_query, 
                           element_id=clause_data['element_id'],
                           embedding=embedding)
                print(f"已更新條款 {clause_data['number']} 的embedding")
            
            print("完成所有embedding的儲存")

    def semantic_search(self, query_text: str, top_k: int = 10, similarity_threshold: float = 0.5) -> List[Dict]:
        """語義搜尋相關條款"""
        try:
            # 為查詢文本生成embedding
            query_embeddings = self.generate_embeddings([query_text])
            if not query_embeddings:
                return []
                
            query_embedding = query_embeddings[0]
            
            # 從Neo4j獲取所有有embedding的條款
            with self.driver.session() as session:
                get_clauses_query = """
                MATCH (c:Clause)
                WHERE c.embedding IS NOT NULL
                RETURN c.number as number,
                       c.title as title,
                       c.content as content,
                       c.embedding as embedding,
                       c.major_title as major_title,
                       CASE
                         WHEN (c)<-[:HAS_CLAUSE]-(:Document {type: 'contract'}) THEN 'contract'
                         WHEN (c)<-[:HAS_CLAUSE]-(:Section {name: '補充投標須知'}) THEN 'supplement_notice'
                         WHEN (c)<-[:HAS_CLAUSE]-(:Section {name: '投標須知'}) THEN 'bidding_notice'
                         WHEN (c)<-[:HAS_CLAUSE]-(:Section {name: '投標須知附錄A'}) THEN 'appendix_a'
                         ELSE 'unknown'
                       END as source
                """
                
                result = session.run(get_clauses_query)
                candidates = []
                all_similarities = []
                
                for record in result:
                    if record['embedding']:
                        similarity = self.cosine_similarity(query_embedding, record['embedding'])
                        all_similarities.append((record['number'], similarity))
                        
                        if similarity >= similarity_threshold:
                            candidates.append({
                                'number': record['number'],
                                'title': record['title'],
                                'content': record['content'],
                                'source': record['source'],
                                'similarity_score': similarity
                            })
                
                # 顯示調試信息
                print(f"語義搜尋調試 - 查詢: '{query_text}'")
                print(f"閾值: {similarity_threshold}, 檢查了 {len(all_similarities)} 個條款")
                if all_similarities:
                    top_similarities = sorted(all_similarities, key=lambda x: x[1], reverse=True)[:5]
                    print(f"前5個相似度: {top_similarities}")
                else:
                    print("沒有找到任何有embedding的條款！")
                
                # 依相似度排序並取前top_k個
                candidates.sort(key=lambda x: x['similarity_score'], reverse=True)
                return candidates[:top_k]
                
        except Exception as e:
            print(f"語義搜尋錯誤: {e}")
            return []

    def reciprocal_rank_fusion(
        self,
        keyword_results: List[Dict],
        semantic_results: List[Dict],
        k: int = 60,
        weight_keyword: float = 1.0,
        weight_semantic: float = 1.0
    ) -> List[Dict]:
        """
        使用 Reciprocal Rank Fusion (RRF) 融合關鍵字和語義搜尋結果

        RRF 公式: score = Σ weight / (k + rank)

        Args:
            keyword_results: 關鍵字搜尋結果（列表，順序即排名）
            semantic_results: 語義搜尋結果（已按相似度排序）
            k: RRF 平滑常數，通常設為 60
            weight_keyword: 關鍵字搜尋的權重
            weight_semantic: 語義搜尋的權重

        Returns:
            融合並按 RRF 分數排序的結果列表
        """
        rrf_scores = {}
        clause_info = {}

        # 處理關鍵字搜尋結果
        for rank, result in enumerate(keyword_results, start=1):
            key = f"{result['source']}_{result['number']}"
            rrf_score = weight_keyword / (k + rank)
            rrf_scores[key] = rrf_scores.get(key, 0) + rrf_score

            # 儲存條款資訊（如果還沒有）
            if key not in clause_info:
                clause_info[key] = {
                    'number': result['number'],
                    'title': result['title'],
                    'content': result['content'],
                    'source': result['source'],
                    'major_title': result.get('major_title', ''),
                    'keyword_match': True,
                    'semantic_match': False,
                    'keyword_rank': rank,
                    'semantic_rank': None,
                    'semantic_score': 0.0
                }
            else:
                clause_info[key]['keyword_match'] = True
                clause_info[key]['keyword_rank'] = rank

        # 處理語義搜尋結果
        for rank, result in enumerate(semantic_results, start=1):
            key = f"{result['source']}_{result['number']}"
            rrf_score = weight_semantic / (k + rank)
            rrf_scores[key] = rrf_scores.get(key, 0) + rrf_score

            # 儲存或更新條款資訊
            if key not in clause_info:
                clause_info[key] = {
                    'number': result['number'],
                    'title': result['title'],
                    'content': result['content'],
                    'source': result['source'],
                    'major_title': result.get('major_title', ''),
                    'keyword_match': False,
                    'semantic_match': True,
                    'keyword_rank': None,
                    'semantic_rank': rank,
                    'semantic_score': result.get('similarity_score', 0.0)
                }
            else:
                clause_info[key]['semantic_match'] = True
                clause_info[key]['semantic_rank'] = rank
                clause_info[key]['semantic_score'] = result.get('similarity_score', 0.0)

        # 合併資訊和分數
        final_results = []
        for key, info in clause_info.items():
            info['rrf_score'] = rrf_scores[key]
            info['final_score'] = rrf_scores[key]  # 使用 RRF 分數作為最終分數
            final_results.append(info)

        # 按 RRF 分數排序
        final_results.sort(key=lambda x: x['rrf_score'], reverse=True)

        # 輸出調試資訊
        print(f"RRF 融合: 關鍵字 {len(keyword_results)} 個 + 語義 {len(semantic_results)} 個 = {len(final_results)} 個唯一條款")
        if final_results:
            top_3 = final_results[:3]
            print(f"Top 3 RRF 分數:")
            for i, r in enumerate(top_3, 1):
                match_type = []
                if r['keyword_match']:
                    match_type.append(f"關鍵字#{r['keyword_rank']}")
                if r['semantic_match']:
                    match_type.append(f"語義#{r['semantic_rank']}")
                print(f"  {i}. {r['number']} - RRF={r['rrf_score']:.4f} ({', '.join(match_type)})")

        return final_results

    def hybrid_search(self, keywords: List[str], query_text: str, top_k: int = 15, use_rrf: bool = True, use_bm25: bool = True) -> List[Dict]:
        """
        混合搜尋：結合關鍵字搜尋和語義搜尋

        Args:
            keywords: 關鍵字列表
            query_text: 查詢文本（用於語義搜尋）
            top_k: 返回前 K 個結果
            use_rrf: 是否使用 RRF 融合（預設 True）
            use_bm25: 是否使用 BM25 全文索引（預設 True，如失敗會自動回退）

        Returns:
            排序後的檢索結果列表
        """
        print(f"執行混合搜尋 - 關鍵字: {keywords}")
        print(f"查詢文本: {query_text}")
        print(f"使用 RRF 融合: {use_rrf}, 使用 BM25: {use_bm25}")

        # 1. 關鍵字搜尋（BM25 或傳統 CONTAINS）
        if use_bm25:
            keyword_results = self.bm25_search(keywords, top_k=100)
        else:
            keyword_results = self.find_related_clauses(keywords)

        print(f"關鍵字搜尋找到 {len(keyword_results)} 個條款")

        # 2. 語義搜尋（擴大搜尋範圍以獲得更好的排名）
        semantic_top_k = max(top_k * 3, 30)  # 至少搜尋 30 個
        semantic_results = self.semantic_search(query_text, top_k=semantic_top_k)
        print(f"語義搜尋找到 {len(semantic_results)} 個條款")

        # 3. 使用 RRF 融合或傳統方法融合
        if use_rrf:
            # 使用 RRF 融合
            final_results = self.reciprocal_rank_fusion(
                keyword_results=keyword_results,
                semantic_results=semantic_results,
                k=60,  # RRF 常數
                weight_keyword=1.0,
                weight_semantic=1.0
            )
        else:
            # 傳統方法（向後相容）
            print("使用傳統評分機制（不推薦）")
            combined_results = {}

            # 添加關鍵字搜尋結果（給予基礎分數1.0）
            for clause in keyword_results:
                key = f"{clause['source']}_{clause['number']}"
                combined_results[key] = {
                    'number': clause['number'],
                    'title': clause['title'],
                    'content': clause['content'],
                    'source': clause['source'],
                    'keyword_match': True,
                    'semantic_score': 0.0,
                    'final_score': 1.0
                }

            # 添加語義搜尋結果
            for clause in semantic_results:
                key = f"{clause['source']}_{clause['number']}"
                if key in combined_results:
                    # 已存在，更新語義分數和最終分數
                    combined_results[key]['semantic_score'] = clause['similarity_score']
                    combined_results[key]['final_score'] = 1.0 + clause['similarity_score']
                else:
                    # 新增語義搜尋結果
                    combined_results[key] = {
                        'number': clause['number'],
                        'title': clause['title'],
                        'content': clause['content'],
                        'source': clause['source'],
                        'keyword_match': False,
                        'semantic_score': clause['similarity_score'],
                        'final_score': clause['similarity_score']
                    }

            # 排序
            final_results = list(combined_results.values())
            final_results.sort(key=lambda x: x['final_score'], reverse=True)

        print(f"混合搜尋最終找到 {len(final_results)} 個條款")
        return final_results[:top_k]

    def extract_keywords_with_llm(
            self,
            main_description,
            check_item,
            deployment_name="o4-mini"):

        prompt = get_keyword_extraction_prompt(main_description, check_item)

        try:
            message_text = [{"role": "system", "content": prompt}]

            response = self.llm_client.chat.completions.create(
                model=deployment_name,
                messages=message_text
            )

            keywords_text = response.choices[0].message.content.strip()
            print(f"LLM原始回應：{keywords_text}")

            keywords = [kw.strip()
                        for kw in keywords_text.split(',') if kw.strip()]
            return keywords

        except Exception as e:
            print(f"LLM關鍵字提取錯誤: {e}")
            return [check_item, main_description]

    def extract_keywords_with_llm_hierarchy(
            self,
            main_description,
            parent_item,
            check_item,
            deployment_name="o4-mini"):
        """
        考慮層次結構的關鍵字提取方法
        """
        try:
            from core.prompt_templates import get_keyword_extraction_hierarchy_prompt
        except ModuleNotFoundError:
            from prompt_templates import get_keyword_extraction_hierarchy_prompt

        prompt = get_keyword_extraction_hierarchy_prompt(main_description, parent_item, check_item)

        try:
            message_text = [{"role": "system", "content": prompt}]

            response = self.llm_client.chat.completions.create(
                model=deployment_name,
                messages=message_text
            )

            keywords_text = response.choices[0].message.content.strip()
            print(f"LLM層次關鍵字原始回應：{keywords_text}")

            keywords = [kw.strip()
                        for kw in keywords_text.split(',') if kw.strip()]
            return keywords

        except Exception as e:
            print(f"LLM層次關鍵字提取錯誤: {e}")
            # 降級處理：使用原始方法
            return self.extract_keywords_with_llm(main_description, check_item, deployment_name)

    def analyze_with_llm(
            self,
            item_info,
            related_clauses,
            main_description,
            parent_item,
            deployment_name="o4-mini",
            project_management_checked=False,
            design_supervision_checked=True,
            user_hint=""):
        """分析條款，支援來自不同文件的條款，並可注入使用者補充說明"""

        # 分類條款
        contract_clauses = [
            c for c in related_clauses if c.get('source') == 'contract']
        bidding_clauses = [c for c in related_clauses if c.get(
            'source') in ['bidding_notice', 'supplement_notice']]
        appendix_a_clauses = [c for c in related_clauses if c.get(
            'source') == 'appendix_a']

        # 組織條款文字
        clauses_text = ""

        if contract_clauses:
            clauses_text += "=== 契約文件相關條款 ===\n"
            for clause in contract_clauses:
                match_info = ""
                if 'keyword_match' in clause:
                    match_type = "關鍵字匹配" if clause['keyword_match'] else "語義匹配"
                    score = clause.get('final_score', 0)
                    match_info = f" [{match_type}, 相關度: {score:.3f}]"

                clauses_text += f"第{clause['number']}條 {clause['title']}{match_info}\n{clause['content']}\n\n"

        if bidding_clauses:
            clauses_text += "=== 投標須知文件相關條款 ===\n"
            for clause in bidding_clauses:
                source_name = "投標須知" if clause['source'] == 'bidding_notice' else "補充投標須知"
                match_info = ""
                if 'keyword_match' in clause:
                    match_type = "關鍵字匹配" if clause['keyword_match'] else "語義匹配"
                    score = clause.get('final_score', 0)
                    match_info = f" [{match_type}, 相關度: {score:.3f}]"

                if clause['source'] == 'bidding_notice':
                    clauses_text += f"[{source_name}] {clause['title']}{match_info}\n{clause['content']}\n\n"
                else:
                    clauses_text += f"[{source_name}] 第{clause['number']}條 {clause['title']}{match_info}\n{clause['content']}\n\n"

        if appendix_a_clauses:
            clauses_text += "=== 投標須知附錄A相關條款 ===\n"
            for clause in appendix_a_clauses:
                match_info = ""
                if 'keyword_match' in clause:
                    match_type = "關鍵字匹配" if clause['keyword_match'] else "語義匹配"
                    score = clause.get('final_score', 0)
                    match_info = f" [{match_type}, 相關度: {score:.3f}]"

                major_title = clause.get('major_title', '')
                display_title = f"{major_title} - {clause['title']}" if major_title and major_title != clause['title'] else clause['title']
                clauses_text += f"[投標須知附錄A] 條款{clause['number']} {display_title}{match_info}\n{clause['content']}\n\n"

        if not related_clauses:
            clauses_text = "未找到相關條款"

        # 獲取當前項目的條款摘要格式
        current_summary = item_info['data'].get('條款摘要', '')
        check_item = item_info['data'].get('檢查項目', '')

        prompt = get_contract_analysis_prompt(main_description, parent_item, check_item, current_summary, clauses_text,
                                             project_management_checked, design_supervision_checked, user_hint)

        # 如果應跳過此項目，返回跳過訊息
        if prompt == "SKIP_ITEM":
            return f"此項目已跳過（案件類型不適用）: {check_item}"

        try:
            message_text = [{"role": "system", "content": prompt}]

            response = self.llm_client.chat.completions.create(
                model=deployment_name,
                messages=message_text
            )

            return response.choices[0].message.content

        except Exception as e:
            return f"LLM分析錯誤: {e}"

    def check_note_condition_with_llm(self, item_data, analysis_result, deployment_name="o4-mini"):
        """使用LLM判斷分析結果是否符合備註條件"""
        note = item_data.get('備註', '').strip()

        # 如果備註是 "info" 或空的，跳過
        if not note or note.lower() == 'info':
            return False

        check_item = item_data.get('檢查項目', item_data.get('主項說明', ''))

        # 使用 LLM 判斷是否達成備註條件
        prompt = f"""你是一個契約審查助手。請判斷以下分析結果是否觸發備註中的提醒條件。

檢查項目：{check_item}
備註條件：{note}

分析結果：
{analysis_result}

**關鍵判斷規則（務必遵守）：**

1. 條款摘要中的勾選符號意義：
   - 「■」代表「勾選」，「□」代表「未勾選」
   - 「■無□有」= 勾選結果為「無」
   - 「□無■有」= 勾選結果為「有」
   - 「■無」= 結果是「無」；「■有」= 結果是「有」

2. 備註條件的觸發邏輯：
   - 備註寫「如有，跳出提醒」→ 只有當條款摘要的**勾選結果為「有」（即出現「■有」）**時，才判斷為「是」
   - 備註寫「如無，跳出提醒」→ 只有當條款摘要的**勾選結果為「無」（即出現「■無」）**時，才判斷為「是」
   - 如果條款摘要為「■無□有」，代表結果是「無」→ 不符合「如有」的觸發條件 → 判斷為「否」

3. 請只看條款摘要中的**勾選結果**來判斷，不要因為分析說明中「提到了相關內容」就判斷為「是」。

請只回答「是」或「否」，並在下一行簡述理由（不超過50字）。
格式：
判斷：是/否
理由：[簡短說明]"""

        try:
            message_text = [{"role": "user", "content": prompt}]

            response = self.llm_client.chat.completions.create(
                model=deployment_name,
                messages=message_text
            )

            llm_response = response.choices[0].message.content.strip()
            print(f"\n備註條件判斷：\n{llm_response}\n")

            # 解析LLM回應
            if '判斷：是' in llm_response or '判斷: 是' in llm_response or llm_response.startswith('是'):
                return True, llm_response
            else:
                return False, llm_response

        except Exception as e:
            print(f"LLM備註判斷錯誤: {e}")
            return False, str(e)

    def generate_review_comment(self, item_number, item_data, related_clauses, analysis_result, deployment_name="o4-mini"):
        """生成專業審查意見"""
        check_item = item_data.get('檢查項目', item_data.get('主項說明', ''))
        note = item_data.get('備註', '')

        # 整理相關條款信息
        clauses_info = ""
        for clause in related_clauses[:5]:  # 取前5個最相關的條款
            source_name = {
                'contract': '契約',
                'bidding_notice': '投標須知',
                'supplement_notice': '補充投標須知',
                'appendix_a': '投標須知附錄A'
            }.get(clause.get('source', ''), '相關文件')

            clauses_info += f"- [{source_name}] 第{clause['number']}條：{clause['title']}\n"

        # 生成審查意見的 Prompt
        prompt = f"""你是一位專業的契約審查專家。請根據以下信息，生成一段正式的審查意見。

檢查項目：{check_item}
備註提醒：{note}

相關條款：
{clauses_info}

分析結果：
{analysis_result}

請生成一段專業的審查意見，格式參考如下範例：
"依投標須知第XX款規定，[說明規定內容]，請計畫於[時間]依期限辦理，[具體建議]。"
"依契約第X條第X款規定，[說明問題或注意事項]，建議洽業主澄清。"

要求：
1. 引用具體條款（如：投標須知第XX款、契約第X條）
2. 清楚說明規定內容或問題點
3. 提出具體建議（使用"請計畫..."、"建議..."等詞彙）
4. 語氣正式、專業
5. 不要包含頁碼（P數字），直接從條款引用開始
6. 控制在150字以內，簡潔有力

請直接輸出審查意見，不要包含其他說明文字。"""

        try:
            message_text = [{"role": "user", "content": prompt}]

            response = self.llm_client.chat.completions.create(
                model=deployment_name,
                messages=message_text
            )

            review_comment = response.choices[0].message.content.strip()
            return review_comment

        except Exception as e:
            print(f"生成審查意見錯誤: {e}")
            return f"依相關規定，本項目{check_item}需特別注意，請計畫審慎評估並依規定辦理。"

    def show_note_alert(self, item_number, item_data, analysis_result, llm_reason, review_comment=""):
        """顯示備註提醒對話框"""
        check_item = item_data.get('檢查項目', item_data.get('主項說明', ''))
        note = item_data.get('備註', '')

        alert_message = f"重要提醒 \n\n"
        alert_message += f"項次：{item_number}\n"
        alert_message += f"檢查項目：{check_item}\n\n"
        alert_message += f"備註條件：{note}\n\n"
        alert_message += f"判斷結果：符合備註條件\n\n"

        if review_comment:
            alert_message += "=" * 50 + "\n"
            alert_message += " 審查意見：\n\n"
            alert_message += f"{review_comment}\n"
            alert_message += "=" * 50 + "\n\n"

        alert_message += f"理由：{llm_reason}\n\n"
        alert_message += "分析內容摘要：\n"
        alert_message += f"{analysis_result[:150]}..."

        print(f"\n{'='*70}")
        print(f"備註提醒")
        print(alert_message)
        print(f"{'='*70}\n")

        # 顯示 GUI 提醒
        try:
            root = tk.Tk()
            root.withdraw()  # 隱藏主視窗
            messagebox.showwarning("檢核項目提醒", alert_message)
            root.destroy()
        except Exception as e:
            print(f"無法顯示GUI提醒: {e}")

    def process_item(self, item_number, deployment_name="o4-mini",
                     project_management_checked=False, design_supervision_checked=True,
                     user_hint=""):
        """處理檢核項目，可選擇性注入使用者補充說明"""
        print(f"=== 處理檢核項目 {item_number} ===")

        item_info = self.find_item_by_number(item_number)
        if not item_info:
            print(f"找不到項次 {item_number}")
            return None

        item_data = item_info['data']
        print(f"項目類型: {item_info['type']}")

        has_children = item_info['type'] in [
            'main', 'sub'] and '子項目' in item_data and item_data['子項目']
        current_summary = item_data.get('條款摘要', '').strip()

        results = []

        # 如果當前項目有條款摘要，就處理當前項目
        if current_summary:
            print(f"處理當前項目 {item_number}...")

            # 獲取主項說明、父項目和檢查項目（完整層次信息）
            if item_info['type'] == 'main':
                main_description = item_data.get('主項說明', '')
                parent_item = ""  # 主項目沒有父項目
                check_item = item_data.get('主項說明', '')
            else:
                main_description = ""
                parent_item = ""

                # 尋找主項說明和父項目信息
                for main_item in self.checklist_data:
                    # 檢查是否為直接子項目
                    for sub in main_item['子項目']:
                        if sub['項次'] == item_number:
                            main_description = main_item['主項說明']
                            parent_item = ""  # 直接子項目沒有父項目
                            break

                        # 檢查是否為子子項目
                        if '子項目' in sub and sub['子項目']:
                            for sub_sub in sub['子項目']:
                                if sub_sub['項次'] == item_number:
                                    main_description = main_item['主項說明']
                                    parent_item = sub.get('檢查項目', '')  # 父項目的檢查項目
                                    break
                            if main_description:  # 如果已找到，跳出外層循環
                                break
                    if main_description:  # 如果已找到，跳出最外層循環
                        break

                check_item = item_data.get('檢查項目', '')

            print(f"主項說明: {main_description}")
            print(f"父項目: {parent_item}")
            print(f"檢查項目: {check_item}")

            # 改用新的關鍵字提取方法，包含層次信息
            keywords = self.extract_keywords_with_llm_hierarchy(
                main_description, parent_item, check_item, deployment_name)
            print(f"LLM提取的關鍵字: {keywords}")

            if parent_item:
                query_text = f"{main_description} {parent_item} {check_item}"
            else:
                query_text = f"{main_description} {check_item}"
            related_clauses = self.hybrid_search(keywords, query_text, top_k=25)

            # 統計不同來源的條款數量
            contract_count = len(
                [c for c in related_clauses if c.get('source') == 'contract'])
            bidding_count = len([c for c in related_clauses if c.get(
                'source') in ['bidding_notice', 'supplement_notice']])
            appendix_a_count = len([c for c in related_clauses if c.get(
                'source') == 'appendix_a'])

            print(f"在契約文件中找到 {contract_count} 個相關條款")
            print(f"在投標須知文件中找到 {bidding_count} 個相關條款")
            print(f"在投標須知附錄A中找到 {appendix_a_count} 個相關條款")
            print(f"總共找到 {len(related_clauses)} 個相關條款")

            for clause in related_clauses:
                source_display = {
                    'contract': '契約文件',
                    'bidding_notice': '投標須知',
                    'supplement_notice': '補充投標須知',
                    'appendix_a': '投標須知附錄A'
                }.get(clause.get('source', ''), '未知來源')

                match_type = "關鍵字" if clause.get('keyword_match', False) else "語義"
                score_info = ""
                if 'final_score' in clause:
                    score_info = f" (分數: {clause['final_score']:.3f})"
                if 'semantic_score' in clause and clause['semantic_score'] > 0:
                    score_info += f" [語義: {clause['semantic_score']:.3f}]"

                print(f"  - [{source_display}] 第{clause['number']}條: {clause['title']} [{match_type}]{score_info}")

            # LLM分析
            print("\n=== LLM分析結果 ===")
            if user_hint:
                print(f"使用者補充說明: {user_hint[:50]}..." if len(user_hint) > 50 else f"使用者補充說明: {user_hint}")
            analysis_result = self.analyze_with_llm(
                item_info, related_clauses, main_description, parent_item, deployment_name,
                project_management_checked, design_supervision_checked, user_hint)
            print(analysis_result)

            # 檢查備註條件
            print("\n=== 檢查備註條件 ===")
            note_result = self.check_note_condition_with_llm(
                item_data, analysis_result, deployment_name)

            # 如果 note_result 是 tuple（有返回值）
            review_comment = ""
            if isinstance(note_result, tuple):
                should_alert, llm_reason = note_result
                if should_alert:
                    # 生成專業審查意見
                    print("\n=== 生成審查意見 ===")
                    review_comment = self.generate_review_comment(
                        item_number, item_data, related_clauses, analysis_result, deployment_name)
                    print(f"審查意見：{review_comment}\n")

                    # 顯示提醒（包含審查意見）
                    self.show_note_alert(item_number, item_data, analysis_result, llm_reason, review_comment)
            elif note_result:  # 舊版相容性
                self.show_note_alert(item_number, item_data, analysis_result, "符合備註條件", "")

            # 將當前項目的結果加入
            current_result = {
                'item_number': item_number,
                'item_info': item_info,
                'main_description': main_description,
                'check_item': check_item,
                'keywords': keywords,
                'related_clauses': related_clauses,
                'analysis': analysis_result,
                'note_alert': note_result if isinstance(note_result, tuple) else (note_result, ""),
                'review_comment': review_comment  # 新增審查意見
            }
            results.append(current_result)
        else:
            print(f"項次 {item_number} 沒有條款摘要，跳過自身分析")

        if has_children:
            print(f"項次 {item_number} 有子項目，開始處理子項目...")
            for sub_item in item_data['子項目']:
                sub_result = self.process_item(sub_item['項次'], deployment_name,
                                             project_management_checked, design_supervision_checked)
                if sub_result:
                    if isinstance(sub_result, list):
                        results.extend(sub_result)
                    else:
                        results.append(sub_result)

        if len(results) == 0:
            return None
        elif len(results) == 1:
            return results[0] 
        else:
            return results

    def batch_process_items(self, item_numbers, deployment_name="o4-mini",
                           project_management_checked=False, design_supervision_checked=True):
        """批量處理多個檢核項目"""
        results = {}
        total_items = len(item_numbers)
        success_count = 0
        error_count = 0

        print(f"\n{'='*70}")
        print(f"開始批量處理 {total_items} 個檢核項目")
        print(f"{'='*70}\n")

        for idx, item_number in enumerate(item_numbers, 1):
            try:
                print(f"\n【進度 {idx}/{total_items}】處理項次 {item_number}...")
                result = self.process_item(item_number, deployment_name,
                                         project_management_checked, design_supervision_checked)
                results[item_number] = result
                success_count += 1
                print(f"\n項次 {item_number} 處理完成")
                print(f"\n{'=' * 70}\n")
            except Exception as e:
                print(f"\n處理項目 {item_number} 時發生錯誤: {e}")
                import traceback
                traceback.print_exc()
                results[item_number] = None
                error_count += 1
                print(f"\n{'=' * 70}\n")

        print(f"\n{'='*70}")
        print(f"批量處理完成！")
        print(f"成功: {success_count}/{total_items}")
        print(f"失敗: {error_count}/{total_items}")
        print(f"{'='*70}\n")

        return results

    def update_json_with_results(self, results, output_file_path):
        updated_data = json.loads(json.dumps(self.checklist_data))

        def update_item_by_number(data, item_number, result_obj):
            """更新指定項次的資料，包含分析結果和審查意見"""
            for main_item in data:
                if main_item["主項次"] == item_number:
                    self.parse_and_update_analysis(main_item, result_obj)
                    return True

                for sub_item in main_item["子項目"]:
                    if sub_item["項次"] == item_number:
                        self.parse_and_update_analysis(sub_item, result_obj)
                        return True

                    if "子項目" in sub_item and sub_item["子項目"]:
                        for sub_sub_item in sub_item["子項目"]:
                            if sub_sub_item["項次"] == item_number:
                                self.parse_and_update_analysis(sub_sub_item, result_obj)
                                return True
            return False

        for item_number, result in results.items():
            if result is None:
                continue

            # 如果結果是list（有子項目的情況）
            if isinstance(result, list):
                for sub_result in result:
                    if isinstance(sub_result, dict) and 'item_number' in sub_result:
                        update_item_by_number(
                            updated_data,
                            sub_result['item_number'],
                            sub_result)
            # 如果結果是單一dict
            elif isinstance(result, dict) and 'analysis' in result:
                update_item_by_number(updated_data, item_number, result)

        # 保存更新後的檔案
        with open(output_file_path, 'w', encoding='utf-8') as f:
            json.dump(updated_data, f, ensure_ascii=False, indent=2)

        print(f"更新後的JSON已保存至: {output_file_path}")

    def parse_and_update_analysis(self, item_data, result_obj):
        """解析LLM分析結果並更新項目資料（包含審查意見）"""
        try:
            # 如果傳入的是字串（舊版相容性）
            if isinstance(result_obj, str):
                analysis_text = result_obj
                review_comment = ""
            # 如果傳入的是 dict（新版）
            elif isinstance(result_obj, dict):
                analysis_text = result_obj.get('analysis', '')
                review_comment = result_obj.get('review_comment', '')
            else:
                return

            # 解析分析結果
            lines = analysis_text.split('\n')

            for line in lines:
                line = line.strip()
                if line.startswith('條款：'):
                    clause_info = line.replace('條款：', '').strip()
                    if clause_info and clause_info != '[]':
                        item_data['條款'] = clause_info
                elif line.startswith('條款摘要：'):
                    summary_info = line.replace('條款摘要：', '').strip()
                    if summary_info:
                        item_data['條款摘要'] = summary_info

            # 如果有審查意見，新增到項目資料中
            if review_comment:
                item_data['審查意見'] = review_comment

            print(f"已更新項次 {item_data.get('項次', item_data.get('主項次', ''))} 的資料")
            if review_comment:
                print(f"  ✅ 已新增審查意見")

        except Exception as e:
            print(f"解析分析結果時發生錯誤: {e}")
            print(f"原始內容: {result_obj}")


def main():
    print("正在開啟案件類型選擇介面...")
    selection_result = show_project_type_selector()

    if selection_result is None or selection_result.get('cancelled', True):
        print("使用者取消操作，程式結束。")
        return

    project_management_checked = selection_result['project_management_checked']
    design_supervision_checked = selection_result['design_supervision_checked']

    print(f"\n=== 使用者選擇的案件類型 ===")
    print(f"{'■' if project_management_checked else '□'} 專管")
    print(f"{'■' if design_supervision_checked else '□'} 設計及監造")

    json_file_path = r"契約審查紀錄表.json"

    # 從 config.json 讀取配置
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)

        azure_endpoint = config['azure_openai']['endpoint']
        azure_api_key = config['azure_openai']['api_key']
        neo4j_uri = config['neo4j']['uri']
        neo4j_username = config['neo4j']['username']
        neo4j_password = config['neo4j']['password']
    except FileNotFoundError:
        print("錯誤: 找不到 config.json 文件")
        return
    except KeyError as e:
        print(f"錯誤: config.json 缺少必要的配置項: {e}")
        return

    system = JSONChecklistQuerySystem(
        json_file_path, azure_endpoint, azure_api_key,
        neo4j_uri, neo4j_username, neo4j_password)

    try:
        print("=== 檢查embedding狀態 ===")
        with system.driver.session() as session:
            embedding_count_query = "MATCH (c:Clause) WHERE c.embedding IS NOT NULL RETURN count(c) as count"
            embedding_result = session.run(embedding_count_query)
            embedding_count = embedding_result.single()['count']
            
            total_count_query = "MATCH (c:Clause) RETURN count(c) as count"
            total_result = session.fenrun(total_count_query)
            total_count = total_result.single()['count']

            sample_query = "MATCH (c:Clause) WHERE c.embedding IS NOT NULL RETURN c.number, size(c.embedding) as embedding_size LIMIT 3"
            sample_result = session.run(sample_query)
            sample_records = list(sample_result)
            if sample_records:
                print("樣本embedding資訊:")
                for record in sample_records:
                    print(f"  條款{record['c.number']}: embedding維度={record['embedding_size']}")
            else:
                print("警告：沒有找到任何有embedding的條款！")
            
            print(f"條款總數: {total_count}, 已有embedding: {embedding_count}")
            
            if embedding_count < total_count:
                print("發現未生成embedding的條款，開始初始化...")
                system.store_embeddings_in_neo4j()
            else:
                print("所有條款已有embedding，可直接使用語義搜尋")

        # =================================================================
        # 選擇測試模式：單個項目測試 或 批量處理
        # =================================================================

        # 模式 1: 測試單個檢核項目（包含備註提醒測試）
        TEST_SINGLE_ITEM = True # 改為 True 啟用單個測試
        SINGLE_TEST_ITEM = "1.4"  # 測試保固期項目（有備註提醒）

        # 模式 2: 批量處理多個項目
        BATCH_PROCESS = False  # 改為 True 啟用批量處理
        BATCH_ITEMS = ["1", "2", "3", "4", "5", "6", "7", "8"]  # 要批量處理的項次

        if TEST_SINGLE_ITEM:
            print("\n=== 測試單個檢核項目 ===")
            result = system.process_item(SINGLE_TEST_ITEM, deployment_name="o4-mini",
                                       project_management_checked=project_management_checked,
                                       design_supervision_checked=design_supervision_checked)
            if result:
                print(f"\n=== 處理結果摘要 ===")
                # 處理可能是list的情況
                if isinstance(result, list) and len(result) > 0:
                    first_result = result[0]
                    print(f"項次: {first_result['item_number']}")
                    print(f"檢查項目: {first_result['check_item']}")
                    print(f"提取關鍵字: {first_result['keywords']}")
                    print(f"找到條款數: {len(first_result['related_clauses'])}")
                    print(f"總共處理了 {len(result)} 個子項目")
                elif isinstance(result, dict):
                    print(f"項次: {result['item_number']}")
                    print(f"檢查項目: {result['check_item']}")
                    print(f"提取關鍵字: {result['keywords']}")
                    print(f"找到條款數: {len(result['related_clauses'])}")
                else:
                    print("結果格式異常")

        if BATCH_PROCESS:
            print("\n=== 批量處理檢核項目 ===")
            batch_results = system.batch_process_items(
                BATCH_ITEMS,
                deployment_name="o4-mini",
                project_management_checked=project_management_checked,
                design_supervision_checked=design_supervision_checked
            )

            # 更新JSON檔案
            print("\n=== 儲存結果到JSON ===")
            system.update_json_with_results(batch_results, "契約審查紀錄表_已填寫.json")
            print("✅ 所有結果已儲存！")

    except Exception as e:
        print(f"主程式錯誤: {e}")
        import traceback
        traceback.print_exc()
    finally:
        system.close()


if __name__ == "__main__":
    main()
