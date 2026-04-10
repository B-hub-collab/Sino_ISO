from neo4j import GraphDatabase
import fitz  # PyMuPDF
import re


class EnhancedGraphBuilder:
    def __init__(self, neo4j_uri, neo4j_username, neo4j_password):
        self.uri = neo4j_uri
        self.auth = (neo4j_username, neo4j_password)
        self.driver = GraphDatabase.driver(self.uri, auth=self.auth)

    def close(self):
        self.driver.close()

    def read_pdf_skip_first_page(
            self,
            pdf_path,
            skip_strikethrough=True,
            skip_first_page=True):
        doc = fitz.open(pdf_path)
        text = ""
        start_page = 1 if skip_first_page else 0
        if skip_first_page:
            start_page = 1
        for page_num in range(start_page, len(doc)):
            page = doc.load_page(page_num)

            if skip_strikethrough:
                text += self.extract_text_without_strikethrough(page)
            else:
                text += page.get_text()

        doc.close()
        return text

    def extract_text_without_strikethrough(self, page):
        text_dict = page.get_text("dict")
        clean_text = ""

        for block in text_dict["blocks"]:
            if "lines" in block:
                for line in block["lines"]:
                    line_text = ""
                    for span in line["spans"]:

                        flags = span.get("flags", 0)

                        has_strikethrough = bool(flags & 16)

                        if not has_strikethrough:
                            line_text += span["text"]
                        else:
                            print(f"跳過刪除線文字: {span['text']}")

                    clean_text += line_text + "\n"

        return clean_text

    def extract_clauses(self, text):
        pattern = r'第([一二三四五六七八九十\d]+)條\s+([^\n]+)'

        matches = re.findall(pattern, text)
        clauses = []

        # 找到所有條款位置
        clause_positions = []
        for match in re.finditer(pattern, text):
            clause_number = match.group(1)
            clause_title = match.group(2).strip()
            start_pos = match.end()

            clause_positions.append({
                'number': clause_number,
                'title': clause_title,
                'start': start_pos
            })

        for i, clause_info in enumerate(clause_positions):
            if i < len(clause_positions) - 1:
                next_start = clause_positions[i + 1]['start'] - \
                    len(clause_positions[i + 1]['title']) - 10
                content = text[clause_info['start']:next_start].strip()
            else:
                content = text[clause_info['start']
                    :clause_info['start'] + 1000].strip()

            clauses.append({
                'number': clause_info['number'],
                'title': clause_info['title'],
                'content': content
            })

        return clauses

    def split_text_by_sections(self, text):
        supplement_pattern = r'補充投標須知\(準用最有利標\)'
        match = re.search(supplement_pattern, text)

        if match:
            split_pos = match.start()
            bidding_notice = text[:split_pos].strip()
            supplement_notice = text[split_pos:].strip()
            print(f"找到分割點：補充投標須知(準用最有利標)")
            return bidding_notice, supplement_notice
        else:
            print("未找到「補充投標須知(準用最有利標)」，全部視為投標須知")
            return text.strip(), ""

    def chinese_to_arabic(self, chinese_num):
        """將中文數字轉換為阿拉伯數字"""
        chinese_digits = {
            '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
            '六': 6, '七': 7, '八': 8, '九': 9, '十': 10
        }
        
        if chinese_num in chinese_digits:
            return chinese_digits[chinese_num]
        
        # 處理十幾、幾十、幾十幾的情況
        if '十' in chinese_num:
            if chinese_num.startswith('十'):  # 十、十一、十二...
                if len(chinese_num) == 1:  # 十
                    return 10
                else:  # 十一、十二...
                    return 10 + chinese_digits.get(chinese_num[1], 0)
            elif chinese_num.endswith('十'):  # 二十、三十...
                return chinese_digits.get(chinese_num[0], 0) * 10
            else:  # 二十一、三十五...
                parts = chinese_num.split('十')
                if len(parts) == 2:
                    tens = chinese_digits.get(parts[0], 0) * 10
                    units = chinese_digits.get(parts[1], 0)
                    return tens + units
        
        # 處理百、千的情況（簡化版）
        if '百' in chinese_num:
            if chinese_num.startswith('一百'):
                return 100 + chinese_digits.get(chinese_num[2:], 0)
            else:
                hundreds = chinese_digits.get(chinese_num[0], 1) * 100
                remainder = chinese_num[2:] if len(chinese_num) > 2 else ''
                return hundreds + chinese_digits.get(remainder, 0)
        
        if '千' in chinese_num:
            return 1000  # 簡化處理
        
        # 無法識別時返回0
        return 0

    def extract_bidding_clauses(self, text):
        # 修改正則表達式，匹配所有中文數字（包括一、二、三等）
        pattern = r'^([一二三四五六七八九十]+|[一二三四五六七八九十]*十[一二三四五六七八九十]*|[一二三四五六七八九十]*百[一二三四五六七八九十]*|[一二三四五六七八九十]*千[一二三四五六七八九十]*)、\s*([^\n]*)'
        
        matches = list(re.finditer(pattern, text, re.MULTILINE))
        clauses = []
        max_clause_number = 0  # 追蹤最大的條文編號

        for i, match in enumerate(matches):
            clause_number = match.group(1)
            title = match.group(2).strip()
            start_pos = match.end()
            
            # 排除可能的子項目（在行首但前面有縮排或空白）
            line_start = text.rfind('\n', 0, match.start()) + 1
            prefix = text[line_start:match.start()]
            
            # 如果前面有明顯的縮排或空白（超過2個字符），跳過
            if len(prefix) > 2:
                continue
            
            # 將中文數字轉換為阿拉伯數字進行遞增檢查
            current_number = self.chinese_to_arabic(clause_number)
            
            # 如果當前編號小於或等於已找到的最大編號，跳過（認為是子項目）
            if current_number <= max_clause_number:
                print(f"跳過子項目編號: {clause_number} (數值: {current_number}, 當前最大: {max_clause_number})")
                continue
            
            # 更新最大編號
            max_clause_number = current_number
            print(f"找到主條文: {clause_number} (數值: {current_number})")

            # 找到內容（到下一個有效條款為止）
            # 尋找下一個有效的主條文位置
            next_start = None
            for j in range(i + 1, len(matches)):
                next_match = matches[j]
                next_clause_number = next_match.group(1)
                next_current_number = self.chinese_to_arabic(next_clause_number)
                
                # 檢查是否是下一個主條文（編號遞增）
                if next_current_number > current_number:
                    # 檢查縮排
                    next_line_start = text.rfind('\n', 0, next_match.start()) + 1
                    next_prefix = text[next_line_start:next_match.start()]
                    if len(next_prefix) <= 2:  # 不是子項目
                        next_start = next_match.start()
                        break
            
            if next_start is not None:
                content = text[start_pos:next_start].strip()
            else:
                # 最後一個條款，取後面所有內容
                content = text[start_pos:].strip()

            # 將原本的 title 和後續 content 合併為完整內容
            full_content = title
            if content.strip():
                full_content += '\n' + content
                
            clauses.append({
                'number': clause_number,
                'title': clause_number,  # 使用數字作為標題
                'content': full_content.strip()  # 完整內容
            })

        return clauses

    def group_bidding_items(self, clauses, group_size=5):
        groups = []
        for i in range(0, len(clauses), group_size):
            group = clauses[i:i + group_size]
            start_num = group[0]['number']
            end_num = group[-1]['number']

            combined_content = ""
            for clause in group:
                combined_content += f"第{clause['number']}條 {clause['title']}\n{clause['content']}\n\n"

            groups.append({
                'group_id': f"{start_num}-{end_num}",
                'title': f"第{start_num}條至第{end_num}條",
                'content': combined_content.strip(),
                'item_count': len(group)
            })

        return groups

    def extract_supplement_clauses(self, text):
        pattern = r'第([一二三四五六七八九十\d]+)條\s+([^\n]*)'

        matches = list(re.finditer(pattern, text))
        clauses = []

        for i, match in enumerate(matches):
            clause_number = match.group(1)
            title = match.group(2).strip()
            start_pos = match.end()

            if i < len(matches) - 1:
                next_start = matches[i + 1].start()
                content = text[start_pos:next_start].strip()
            else:
                content = text[start_pos:].strip()

            clauses.append({
                'number': clause_number,
                'title': title,
                'content': content
            })

        return clauses

    def chinese_major_to_arabic(self, chinese_num):
        """將主項目的中文大寫數字（壹、貳、參等）轉換為阿拉伯數字"""
        chinese_major_digits = {
            '壹': 1, '貳': 2, '參': 3, '肆': 4, '伍': 5,
            '陸': 6, '柒': 7, '捌': 8, '玖': 9, '拾': 10
        }
        return chinese_major_digits.get(chinese_num, 0)

    def extract_appendix_a_clauses(self, text):
        """提取投標須知附錄A的條款（壹、貳、參等主項目及其子項目）"""
        # 主項目模式：壹、貳、參等
        major_pattern = r'^([壹貳參肆伍陸柒捌玖拾]+)、\s*([^\n]+)'
        # 子項目模式：一、二、三等
        minor_pattern = r'^\s*([一二三四五六七八九十百千]+)、\s*([^\n]*)'

        major_matches = list(re.finditer(major_pattern, text, re.MULTILINE))
        clauses = []

        for i, major_match in enumerate(major_matches):
            major_number = major_match.group(1)
            major_title = major_match.group(2).strip()
            major_start = major_match.end()

            # 找到下一個主項目的位置
            if i < len(major_matches) - 1:
                major_end = major_matches[i + 1].start()
            else:
                major_end = len(text)

            # 提取當前主項目的內容區域
            major_content = text[major_start:major_end]

            # 在此主項目下尋找子項目
            minor_matches = list(re.finditer(minor_pattern, major_content, re.MULTILINE))

            if minor_matches:
                # 有子項目的情況
                for j, minor_match in enumerate(minor_matches):
                    minor_number = minor_match.group(1)
                    minor_title = minor_match.group(2).strip()
                    minor_start = minor_match.end()

                    # 找到下一個子項目的位置
                    if j < len(minor_matches) - 1:
                        minor_end = minor_matches[j + 1].start()
                    else:
                        minor_end = len(major_content)

                    # 提取子項目內容
                    minor_content = major_content[minor_start:minor_end].strip()

                    # 組合完整內容（標題 + 內容）
                    full_content = minor_title
                    if minor_content:
                        full_content += '\n' + minor_content

                    # 轉換編號為數字格式（如：2.1, 2.2）
                    major_num = self.chinese_major_to_arabic(major_number)
                    minor_num = self.chinese_to_arabic(minor_number)

                    clauses.append({
                        'number': f"{major_num}.{minor_num}",
                        'major_number': major_number,
                        'major_title': major_title,
                        'minor_number': minor_number,
                        'title': f"{major_title} - {minor_number}",
                        'content': full_content.strip()
                    })
            else:
                # 沒有子項目的情況，整個主項目作為一個條款
                major_num = self.chinese_major_to_arabic(major_number)
                clauses.append({
                    'number': str(major_num),
                    'major_number': major_number,
                    'major_title': major_title,
                    'minor_number': None,
                    'title': major_title,
                    'content': major_content.strip()
                })

        return clauses

    def create_appendix_a_document(self, pdf_path, skip_strikethrough=True):
        """建立投標須知附錄A的圖譜結構"""
        # 讀取PDF，跳過第一頁
        text = self.read_pdf_skip_first_page(
            pdf_path, skip_strikethrough, skip_first_page=True)
        filename = pdf_path.split('/')[-1].replace('.pdf', '')

        # 提取附錄A條款
        clauses = self.extract_appendix_a_clauses(text)
        print(f"提取到 {len(clauses)} 個附錄A條款")

        with self.driver.session() as session:
            # 建立文件節點
            doc_query = """
            CREATE (d:Document {
                name: $name,
                type: 'appendix_a'
            })
            RETURN d
            """
            session.run(doc_query, name=filename)
            print(f"建立文件節點: {filename}")

            # 建立投標須知附錄A的Section節點
            section_query = """
            MATCH (d:Document {name: $doc_name})
            CREATE (s:Section {
                name: '投標須知附錄A',
                type: 'appendix_a',
                total_clauses: $total_clauses
            })
            CREATE (d)-[:HAS_SECTION]->(s)
            RETURN s
            """
            session.run(section_query,
                       doc_name=filename,
                       total_clauses=len(clauses))
            print(f"建立投標須知附錄A節點，共 {len(clauses)} 個條款")

            # 建立條款節點（包含主項目和子項目的層級結構）
            for clause in clauses:
                clause_query = """
                MATCH (s:Section {name: '投標須知附錄A'})
                WHERE (s)<-[:HAS_SECTION]-(:Document {name: $doc_name})
                CREATE (c:Clause {
                    number: $number,
                    major_number: $major_number,
                    major_title: $major_title,
                    minor_number: $minor_number,
                    title: $title,
                    content: $content
                })
                CREATE (s)-[:HAS_CLAUSE]->(c)
                RETURN c.number, c.title
                """

                result = session.run(clause_query,
                                   doc_name=filename,
                                   number=clause['number'],
                                   major_number=clause['major_number'],
                                   major_title=clause['major_title'],
                                   minor_number=clause.get('minor_number'),
                                   title=clause['title'],
                                   content=clause['content'])

                record = result.single()
                if record:
                    print(f"建立條款: {record['c.number']} - {record['c.title']}")

        return filename

    def create_bidding_document(
            self,
            pdf_path,
            skip_strikethrough=True):
        """建立投標文件的圖譜結構"""
        text = self.read_pdf_skip_first_page(
            pdf_path, skip_strikethrough, skip_first_page=False)
        filename = pdf_path.split('/')[-1].replace('.pdf', '')

        bidding_text, supplement_text = self.split_text_by_sections(text)

        print(f"投標須知文本長度: {len(bidding_text)}")
        print(f"補充投標須知文本長度: {len(supplement_text)}")

        with self.driver.session() as session:
            doc_query = """
            CREATE (d:Document {
                name: $name,
                type: 'bidding_document'
            })
            RETURN d
            """

            session.run(doc_query, name=filename)
            print(f"建立文件節點: {filename}")

            if bidding_text:
                clauses = self.extract_bidding_clauses(bidding_text)
                print(f"提取到 {len(clauses)} 條投標須知條款")

                section_query = """
                MATCH (d:Document {name: $doc_name})
                CREATE (s:Section {
                    name: '投標須知',
                    type: 'bidding_notice',
                    total_clauses: $total_clauses
                })
                CREATE (d)-[:HAS_SECTION]->(s)
                RETURN s
                """

                session.run(section_query,
                            doc_name=filename,
                            total_clauses=len(clauses))
                print(f"建立投標須知節點，共 {len(clauses)} 個條款")

                # 建立個別條款節點（不再分組）
                for clause in clauses:
                    clause_query = """
                    MATCH (s:Section {name: '投標須知'})
                    WHERE (s)<-[:HAS_SECTION]-(:Document {name: $doc_name})
                    CREATE (c:Clause {
                        number: $number,
                        title: $title,
                        content: $content
                    })
                    CREATE (s)-[:HAS_CLAUSE]->(c)
                    RETURN c.number, c.title
                    """

                    result = session.run(clause_query,
                                         doc_name=filename,
                                         number=clause['number'],
                                         title=clause['title'],
                                         content=clause['content'])

                    record = result.single()
                    if record:
                        print(f"建立條款: 第{record['c.number']}條 - {record['c.title']}")

            if supplement_text:
                clauses = self.extract_supplement_clauses(supplement_text)

                # 建立補充投標須知主節點
                supplement_query = """
                MATCH (d:Document {name: $doc_name})
                CREATE (s:Section {
                    name: '補充投標須知',
                    type: 'supplement_notice',
                    total_clauses: $total_clauses
                })
                CREATE (d)-[:HAS_SECTION]->(s)
                RETURN s
                """

                session.run(supplement_query,
                            doc_name=filename,
                            total_clauses=len(clauses))
                print(f"建立補充投標須知節點，共 {len(clauses)} 個條款")

                # 建立條款節點
                for clause in clauses:
                    clause_query = """
                    MATCH (s:Section {name: '補充投標須知'})
                    WHERE (s)<-[:HAS_SECTION]-(:Document {name: $doc_name})
                    CREATE (c:Clause {
                        number: $number,
                        title: $title,
                        content: $content
                    })
                    CREATE (s)-[:HAS_CLAUSE]->(c)
                    RETURN c.number, c.title
                    """

                    result = session.run(clause_query,
                                         doc_name=filename,
                                         number=clause['number'],
                                         title=clause['title'],
                                         content=clause['content'])

                    record = result.single()
                    if record:
                        print(f"建立條款: 第{record['c.number']}條 - {record['c.title']}")

        return filename

    def create_document_and_clauses(self, pdf_path, skip_strikethrough=True):
        text = self.read_pdf_skip_first_page(pdf_path, skip_strikethrough)
        filename = pdf_path.split('/')[-1].replace('.pdf', '')

        # 提取條款
        clauses = self.extract_clauses(text)

        with self.driver.session() as session:
            # 建立文件節點
            doc_query = """
            CREATE (d:Document {
                name: $name,
                total_clauses: $total_clauses,
                type: 'contract'
            })
            RETURN d
            """

            session.run(doc_query,
                        name=filename,
                        total_clauses=len(clauses))

            for clause in clauses:
                clause_query = """
                MATCH (d:Document {name: $doc_name})
                CREATE (c:Clause {
                    number: $number,
                    title: $title,
                    content: $content
                })
                CREATE (d)-[:HAS_CLAUSE]->(c)
                RETURN c.number, c.title
                """

                result = session.run(clause_query,
                                     doc_name=filename,
                                     number=clause['number'],
                                     title=clause['title'],
                                     content=clause['content'])

                record = result.single()
                if record:
                    print(f"建立條款: 第{record['c.number']}條 - {record['c.title']}")

        return len(clauses)


def main():
    # 從 config.json 讀取配置
    import json
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
        neo4j_uri = config['neo4j']['uri']
        neo4j_username = config['neo4j']['username']
        neo4j_password = config['neo4j']['password']
    except FileNotFoundError:
        print("錯誤: 找不到 config.json 文件")
        return
    except KeyError as e:
        print(f"錯誤: config.json 缺少必要的配置項: {e}")
        return

    builder = EnhancedGraphBuilder(neo4j_uri, neo4j_username, neo4j_password)
    bidding_pdf_path = r"D:\中興ISO\公告版_台中藍線BD03_20251009\_投標須知\02-00_投標須知(BD03)_臺中市政府投標須知範本-適用及準用最有利標-修正.pdf"
    contract_pdf_path = r"D:\中興ISO\公告版_台中藍線BD03_20251009\03_採購契約\03_00臺中捷運藍線建設計畫BD03標細部設計及監造委託技術服務契約.pdf" # 契約文件路徑
    appendix_a_pdf_path = r"D:\中興ISO\公告版_台中藍線BD03_20251009\02-01_投標須知_附錄A_評選辦法.pdf"  # 投標須知附錄A文件路徑
    skip_strikethrough = True

    try:
        print("開始處理文件...")

        # 1. 處理投標須知文件（包含投標須知和補充投標須知）
        print("\n=== 處理投標須知文件 ===")
        bidding_filename = builder.create_bidding_document(
            bidding_pdf_path, skip_strikethrough)
        print(f"✓ 完成投標須知文件: {bidding_filename}")

        # 2. 處理契約文件
        print("\n=== 處理契約文件 ===")
        contract_clause_count = builder.create_document_and_clauses(
            contract_pdf_path, skip_strikethrough)
        print(f"✓ 完成契約文件，建立了 {contract_clause_count} 個條款節點")

        # 3. 處理投標須知附錄A文件（如果路徑存在）
        if appendix_a_pdf_path != r"請填入投標須知附錄A的PDF路徑":
            print("\n=== 處理投標須知附錄A文件 ===")
            appendix_a_filename = builder.create_appendix_a_document(
                appendix_a_pdf_path, skip_strikethrough)
            print(f"✓ 完成投標須知附錄A文件: {appendix_a_filename}")

        print("\n在Neo4j Browser執行以下查詢來查看結果:")
        print("MATCH (d:Document {type: 'bidding_document'})-[:HAS_SECTION]->(s:Section) RETURN d, s")

        print("\n# 完整蓋覽")
        print

        print("\n# 查看投標須知條款")
        print( "MATCH (s:Section {name: '投標須知'})-[:HAS_CLAUSE]->(c:Clause) RETURN s, c")

        print("\n# 查看補充投標須知條款")
        print("MATCH (s:Section {name: '補充投標須知'})-[:HAS_CLAUSE]->(c:Clause) RETURN s, c")

        print("\n# 查看投標須知附錄A條款")
        print("MATCH (s:Section {name: '投標須知附錄A'})-[:HAS_CLAUSE]->(c:Clause) RETURN s, c")

        print("\n# 查看契約文件條款")
        print( "MATCH (d:Document {type: 'contract'})-[:HAS_CLAUSE]->(c:Clause) RETURN d, c")

        print("\n# 查看所有內容概覽")
        print("MATCH (n) RETURN labels(n), count(n)")

    except Exception as e:
        print(f" 錯誤: {e}")
        import traceback
        traceback.print_exc()
    finally:
        builder.close()
# MATCH (n) DETACH DELETE n

if __name__ == "__main__":
    main()
