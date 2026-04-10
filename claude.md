# Contract Checker App - Claude 開發指南

## 專案概述

這是一個基於 AI 的工程契約審查系統，整合了 PDF 文件處理、Neo4j 圖資料庫、語義搜尋和 LLM 分析。主要用於自動化檢查工程採購契約、投標文件的合規性。

### 核心技術棧
- **GUI**: Tkinter (Python 內建)
- **PDF 處理**: pdfplumber (表格提取), PyMuPDF/fitz (文本提取)
- **資料庫**: Neo4j 圖資料庫 (雲端 Aura 服務)
- **AI/LLM**: Azure OpenAI API (GPT-4/4-mini + text-embedding-ada-002)
- **數值計算**: NumPy (向量運算、相似度計算)

---

## 專案架構

```
contract_checker_app/
├── main_app.py                    # 主程式 - Tkinter GUI 介面 (770行)
├── core/                          # 核心模組
│   ├── pdf2json.py               # PDF表格轉JSON (162行)
│   ├── doc2graph.py              # PDF文件上傳至Neo4j圖資料庫 (639行)
│   ├── LLMcheck.py               # AI檢查引擎 - 混合搜尋+LLM分析 (1064行)
│   ├── prompt_templates.py       # LLM提示詞模板庫 (272行)
│   └── project_type_selector.py  # 案件類型選擇器GUI (124行)
├── config.json                    # 運行時配置 (敏感資訊，不納入版控)
├── config.template.json          # 配置範本
├── requirements.txt              # Python依賴清單
├── build.spec                    # PyInstaller打包設定
└── output/                       # JSON輸出目錄
```

---

## 三階段工作流程

### 步驟 1: 測試表單 PDF → JSON
**模組**: `core/pdf2json.py`

**功能**:
- 將契約審查紀錄表 PDF 轉換為階層化 JSON
- 支援三層級結構：主項次 → 子項目 → 子子項目
- 自動識別項次格式：
  - 整數 (1, 2, 3...)：主項次
  - 浮點數 (1.1, 1.2...)：子項目
  - 字母 (1.1.a, 1.1.b...)：子子項目

**輸出格式**:
```json
[
  {
    "主項次": "1",
    "主項說明": "計畫內容概要",
    "備註": "",
    "子項目": [
      {
        "項次": "1.1",
        "檢查項目": "計畫名稱及地點",
        "條款": "",
        "條款摘要": "■無□有",
        "備註": "",
        "子項目": []
      }
    ]
  }
]
```

**重要函數**:
- `pdf_to_hierarchical_json(pdf_path, output_path, skip_first_page=True)`: 主轉換函數
- `parse_item_number(text)`: 解析項次格式 (整數/浮點/字母)

---

### 步驟 2: 契約文件 → Neo4j 圖資料庫
**模組**: `core/doc2graph.py`

**功能**:
- 解析三種文件類型並建立圖結構：
  1. **契約文件**: 「第X條」格式條款
  2. **投標須知**: 中文數字格式 (一、二、三...)
  3. **投標須知附錄A**: 大寫中文 (壹、貳、參...) + 二層級結構
- 支援移除刪除線文字 (可配置)
- 自動生成語義向量 (embedding) 供後續搜尋使用

**Neo4j 圖結構**:
```
Document (文件節點)
  └─ HAS_SECTION → Section (章節節點)
      └─ HAS_CLAUSE → Clause (條款節點)
          ├── number: 條款編號
          ├── title: 條款標題
          ├── content: 條款內容
          ├── embedding: 語義向量 (1536維)
          └── major_title: 主項目標題 (附錄A專用)
```

**核心類別**: `EnhancedGraphBuilder`

**重要方法**:
- `create_document_and_clauses()`: 契約文件上傳
- `create_bidding_document()`: 投標須知上傳
- `create_appendix_a_document()`: 附錄A上傳
- `extract_text_without_strikethrough()`: 移除刪除線文字
- `extract_clauses()`: 提取「第X條」格式條款
- `extract_bidding_clauses()`: 提取中文數字條款
- `extract_appendix_a_clauses()`: 提取兩層級附錄A條款

**數字轉換**:
- `chinese_to_arabic()`: 小寫中文 → 阿拉伯數字 (一二三 → 123)
- `chinese_major_to_arabic()`: 大寫中文 → 阿拉伯數字 (壹貳參 → 123)

---

### 步驟 3: 執行檢查 - LLM 分析
**模組**: `core/LLMcheck.py`

**功能**:
- 混合搜尋：關鍵字搜尋 + 語義搜尋
- LLM 驅動的契約條款分析
- 支援案件類型篩選 (專管/設計監造)
- 自動提取關鍵字並匹配相關條款

**核心類別**: `JSONChecklistQuerySystem`

**搜尋流程**:
```
1. 從 JSON 查詢檢查項目 (by 項次編號)
   ↓
2. 判斷是否跳過 (根據案件類型: 專管/設計監造)
   ↓
3. 提取關鍵字 (LLM 或直接使用檢查項目文字)
   ↓
4. 執行混合搜尋
   ├─ 關鍵字搜尋 (Neo4j Cypher 查詢)
   └─ 語義搜尋 (embedding 餘弦相似度)
   ↓
5. 合併結果 (評分、去重、排序)
   ↓
6. LLM 分析 (使用 prompt_templates.py)
   ↓
7. 返回結果：條款、條款摘要、分析說明
```

**混合搜尋評分機制**:
- **僅關鍵字匹配**: 基礎分 1.0
- **關鍵字 + 語義**: 基礎分 1.0 + 語義相似度 (0-1)
- **僅語義匹配**: 語義相似度 (需達閾值 0.5)

**重要方法**:
- `process_item()`: 處理單一檢查項目 (主入口)
- `hybrid_search()`: 混合搜尋
- `semantic_search()`: 語義搜尋 (embedding 相似度)
- `find_related_clauses()`: 關鍵字搜尋
- `analyze_with_llm()`: 調用 LLM 分析
- `generate_embeddings()`: 批次生成語義向量
- `store_embeddings_in_neo4j()`: 儲存向量至 Neo4j

---

## 提示詞系統 (core/prompt_templates.py)

### 核心提示詞函數

#### 1. `get_contract_analysis_prompt()`
用於 LLM 分析契約條款，包含詳細的分析指導原則。

**提示詞特點**:
- **嚴格格式控制**: 強制輸出「條款: / 條款摘要: / 分析說明:」三段式
- **案件類型感知**: 區分專管/設計監造，跳過不相關項目
- **層次結構理解**: 理解主項→父項→檢查項目的三層關係
- **防止格式混淆**: 禁止使用其他項目的條款摘要格式

**關鍵判斷邏輯**:

1. **後續擴充判斷** (`□無□有(NTD    )` 格式):
   - **判斷標準**: 看條文「冒號後」或「括號後」是否有填寫實際內容
   - **有結構 ≠ 有內容**: 即使條文提到「保留增購權利」，但未填寫具體金額/數量/期間 → 判斷為「■無」
   - **只有明確填寫才算「有」**: 如「NTD 1,000,000元」、「數量100件」、「期間1年」
   - 範例:
     ```
     條文: "本採購保留未來向得標廠商增購之權利，擬增購之項目及內容：______"
     → 冒號後空白/底線/未填寫 → 判斷為「■無□有」
     ```

2. **甲方辦理事項判斷** (`□無□有` 格式):
   - 有標題結構但內容空白 → 「■無」
   - 註明「無者免填」且實際未填寫 → 「無」

3. **計價週期判斷**:
   - 「每一個月計價」/「每月估驗」/「按月給付」→ 勾選並填入「1」
   - 「每季」→ 填入「3」
   - 「每半年」→ 填入「6」

4. **施工進度 vs 監造進度**:
   - 「按實際施工進度百分比計付」→ 勾選「■施工進度」
   - 「按監造工作完成進度計付」→ 勾選「■監造進度」
   - 「監造服務費按施工進度計價」→ 只勾選「■施工進度」

5. **保險條款判斷**:
   - 根據檢查項目的保險類型，精確識別對應條款
   - 區分專業責任險、營造綜合險等不同保險類型
   - 嚴格按條款原文填寫保險金額

#### 2. `get_keyword_extraction_prompt()`
基礎關鍵字提取，用於簡單項目。

#### 3. `get_keyword_extraction_hierarchy_prompt()`
層次感知的關鍵字提取，用於多層級項目。

**雙層關鍵字策略**:
- **特異性關鍵字** (3-4個): 結合主項+父項+檢查項目，防止跨主題混淆
- **通用關鍵字** (3-4個): 基本詞彙，擴大搜尋範圍

範例:
```
輸入: 主項=保險，父項=專責險保險條件，檢查項目=保險金額及自負額
輸出: 專責險,專業責任險,保險金額,自負額,保險條件,金額,責任險
```

#### 4. `should_skip_item()`
判斷是否應跳過某檢查項目 (根據案件類型)。

**跳過邏輯**:
- 兩者都選 (專管+設計監造) → 不跳過任何項目
- 只選設計監造 → 跳過純專管項目
- 只選專管 → 跳過純監造項目
- 都不選 → 跳過所有項目

---

## 配置管理

### config.json 結構
```json
{
  "neo4j": {
    "uri": "neo4j+s://xxxxxx.databases.neo4j.io",
    "username": "neo4j",
    "password": "your-password"
  },
  "azure_openai": {
    "endpoint": "https://your-resource.openai.azure.com/",
    "api_key": "your-api-key",
    "api_version": "2025-01-01-preview",
    "deployment_name": "o4-mini"
  },
  "app_settings": {
    "default_output_folder": "output",
    "skip_strikethrough": true,           // 是否跳過刪除線文字
    "skip_first_page_contract": true,     // 契約文件是否跳過首頁
    "skip_first_page_bidding": false,     // 投標須知是否跳過首頁
    "batch_size_embedding": 10,           // embedding批次大小
    "semantic_search_threshold": 0.5,     // 語義搜尋相似度閾值
    "semantic_search_top_k": 10,          // 語義搜尋返回數量
    "hybrid_search_top_k": 25             // 混合搜尋返回數量
  },
  "project_types": {
    "available_types": ["project_management", "design_supervision"]
  }
}
```

### 首次設定流程
1. 應用啟動時檢查 `config.json` 是否存在
2. 不存在 → 顯示 `SetupDialog` 引導用戶填寫
3. 用戶輸入 Neo4j 和 Azure OpenAI 連線資訊
4. 自動生成並保存 `config.json`
5. 後續啟動直接載入配置

---

## 主程式 GUI (main_app.py)

### 主要類別

#### 1. ConfigManager
配置文件管理器，負責載入和創建 config.json。

#### 2. SetupDialog
首次設定對話框，收集：
- Neo4j URI、使用者名稱、密碼
- Azure OpenAI 端點、API Key

#### 3. ContractCheckerApp
主應用程式，包含：
- **三個分頁**: 對應三步驟工作流
- **執行緒化操作**: 避免長時間運算卡住 UI
- **狀態列**: 實時顯示運行狀態
- **錯誤處理**: 友善的錯誤訊息顯示

### GUI 分頁設計

**分頁 1: 步驟 1 - 測試表單**
- 選擇契約審查紀錄表 PDF
- 執行轉換 → 生成 JSON
- 顯示 JSON 路徑

**分頁 2: 步驟 2 - 契約文件**
- 上傳契約文件 PDF
- 上傳投標須知 PDF
- 上傳投標須知附錄A (選填)
- 執行上傳 → 建立圖資料庫
- 清空資料庫功能 (二次確認)

**分頁 3: 步驟 3 - 執行檢查**
- 選擇檢查清單 JSON
- 輸入項次編號 (如 "1.1.a")
- 選擇案件類型 (專管/設計監造)
- 執行檢查 → 顯示 LLM 分析結果

---

## 開發指南

### 新增功能時的注意事項

#### 1. 修改提示詞 (prompt_templates.py)
- **測試影響範圍**: 提示詞變更會影響所有檢查項目的分析結果
- **保持格式一致性**: 確保輸出格式符合「條款: / 條款摘要: / 分析說明:」
- **增加新判斷邏輯**: 在對應的判斷邏輯區塊添加，使用醒目的標題 (如 `**新增邏輯**(格式)`)

範例:
```python
**新增邏輯判斷**(針對「□無□有」格式):
- 判斷標準說明
- 具體範例
- 特殊情況處理
```

#### 2. 修改搜尋邏輯 (LLMcheck.py)
- **關鍵字搜尋**: 修改 `find_related_clauses()` 的 Cypher 查詢
- **語義搜尋**: 調整 `semantic_search()` 的相似度閾值
- **混合搜尋**: 修改 `hybrid_search()` 的評分機制

#### 3. 新增文件類型 (doc2graph.py)
- 實作新的條款提取函數 (如 `extract_xxx_clauses()`)
- 實作數字轉換函數 (如需要)
- 在 `EnhancedGraphBuilder` 添加對應的建檔方法
- 更新 GUI (main_app.py) 添加上傳入口

#### 4. 修改 JSON 結構 (pdf2json.py)
- 更新 `pdf_to_hierarchical_json()` 的解析邏輯
- 確保與 `LLMcheck.py` 的 `find_item_by_number()` 相容
- 測試多層級巢狀結構

### 調試技巧

#### 1. 查看 Neo4j 資料庫內容
在 Neo4j Browser 執行:
```cypher
// 查看所有文件和條款數量
MATCH (d:Document)
OPTIONAL MATCH (d)-[:HAS_SECTION]->(s:Section)-[:HAS_CLAUSE]->(c:Clause)
RETURN d.name, count(c) as clause_count

// 查看特定條款
MATCH (c:Clause {number: "第5條"})
RETURN c.title, c.content

// 查看是否已生成 embedding
MATCH (c:Clause)
WHERE c.embedding IS NOT NULL
RETURN count(c) as embedded_clauses
```

#### 2. 測試關鍵字搜尋
在 `LLMcheck.py` 的 `find_related_clauses()` 添加 print:
```python
print(f"搜尋關鍵字: {keywords}")
print(f"找到 {len(results)} 筆結果")
for r in results[:3]:
    print(f"  - {r['number']}: {r['title']}")
```

#### 3. 測試語義搜尋
在 `semantic_search()` 添加 print:
```python
print(f"查詢向量維度: {len(query_embedding)}")
print(f"相似度閾值: {threshold}")
print(f"找到 {len(results)} 筆相似條款")
```

#### 4. 檢查 LLM 輸出格式
在 `analyze_with_llm()` 後:
```python
print("=== LLM 原始輸出 ===")
print(response)
print("===================")
```

---

## 常見問題與解決方案

### 1. Neo4j 連線失敗
**錯誤**: `Cannot resolve address xxx.databases.neo4j.io:7687`

**解決方案**:
- 檢查 Neo4j Aura 實例是否過期或暫停
- 登入 [Neo4j Aura Console](https://console.neo4j.io/) 確認狀態
- 測試網路連線: `nslookup xxx.databases.neo4j.io`
- 檢查防火牆是否阻擋 port 7687
- 更新 `config.json` 中的連線資訊

### 2. Embedding 生成失敗
**錯誤**: `RateLimitError` 或 `InvalidRequestError`

**解決方案**:
- 檢查 Azure OpenAI API 配額是否用盡
- 降低 `batch_size_embedding` (config.json)
- 檢查文本長度是否超過 token 限制 (8191 tokens)
- 確認 deployment_name 正確 (應為 text-embedding-ada-002)

### 3. LLM 輸出格式不符
**錯誤**: 無法解析 LLM 輸出

**解決方案**:
- 檢查 prompt_templates.py 中的格式指示是否清晰
- 在提示詞中強調輸出格式範例
- 使用更嚴格的格式約束詞彙 (如「嚴格按照以下格式」)
- 檢查是否為 GPT-4 模型 (GPT-3.5 可能格式遵守較差)

### 4. PDF 解析錯誤
**錯誤**: 條款提取不完整或錯誤

**解決方案**:
- 檢查 PDF 文字是否為掃描圖片 (需要 OCR)
- 調整正則表達式匹配規則
- 確認是否需要跳過首頁 (config.json)
- 檢查刪除線文字設定 (skip_strikethrough)

### 5. 案件類型篩選不正確
**錯誤**: 應跳過的項目仍被處理

**解決方案**:
- 檢查 `should_skip_item()` 邏輯
- 確認檢查項目中是否包含「專管」或「監造」關鍵字
- 檢查 ProjectTypeSelector 的返回值是否正確
- 在 `process_item()` 添加 debug print 確認跳過邏輯

---

## 性能優化建議

### 1. Embedding 生成優化
- **批次處理**: 已實作批次大小 10
- **快取策略**: 考慮儲存已生成的 embedding，避免重複計算
- **並行處理**: 使用 asyncio 並行調用 Azure OpenAI API

### 2. 搜尋優化
- **索引優化**: 在 Neo4j 為常用屬性建立索引
  ```cypher
  CREATE INDEX clause_number FOR (c:Clause) ON (c.number)
  CREATE INDEX clause_content FOR (c:Clause) ON (c.content)
  ```
- **快取搜尋結果**: 相同關鍵字在短時間內不重複搜尋
- **提前終止**: 達到足夠數量的高分結果時提前結束

### 3. GUI 響應性
- **進度條**: 為長時間操作添加進度條顯示
- **取消按鈕**: 允許用戶中途取消操作
- **異步更新**: 使用 queue 在執行緒間傳遞進度訊息

---

## 擴展方向

### 1. 批次檢查功能
實作一次檢查所有項目的功能:
```python
def batch_process_all_items(self, json_path, project_types):
    """批次處理所有檢查項目"""
    results = []
    for main_item in self.checklist_data:
        for sub_item in main_item["子項目"]:
            result = self.process_item(sub_item["項次"], ...)
            results.append(result)
    return results
```

### 2. 結果匯出功能
將檢查結果匯出為 Excel 或 PDF 報告。

### 3. 歷史紀錄功能
記錄每次檢查的結果，支援比對和追蹤變更。

### 4. 多語言支援
擴展至英文契約或其他語言的文件。

### 5. 更多文件格式
支援 Word (DOCX)、Excel 等格式的契約文件。

---

## 安全與隱私

### 敏感資訊保護
- `config.json` 包含 Neo4j 密碼和 API Key，**不應納入版控**
- 建議使用環境變數或密鑰管理服務
- 定期更新密碼和 API Key

### 資料隱私
- 契約文件可能包含敏感的商業資訊
- 確保 Neo4j 資料庫訪問權限設定正確
- 考慮資料加密和訪問日誌

---

## 技術決策記錄

### 為什麼使用 Neo4j 圖資料庫？
- **層次結構自然表達**: 文件→章節→條款的關係用圖模型清晰表達
- **靈活的查詢**: Cypher 查詢語言適合複雜的關聯查詢
- **embedding 支援**: 可直接儲存向量，支援相似度搜尋

### 為什麼使用混合搜尋？
- **關鍵字搜尋**: 精確匹配，適合明確指定的術語
- **語義搜尋**: 理解語意相似性，捕捉同義表達
- **互補優勢**: 結合兩者可提升搜尋召回率和準確率

### 為什麼使用 Tkinter 而非 Web 介面？
- **桌面應用定位**: 目標用戶為企業內部使用
- **無需伺服器**: 簡化部署，降低維護成本
- **離線運行**: 除 API 調用外可離線使用
- **輕量級**: 無需學習前端框架

---

## 測試建議

### 單元測試
- 測試 `parse_item_number()` 的各種格式
- 測試 `chinese_to_arabic()` 的轉換正確性
- 測試 `should_skip_item()` 的跳過邏輯

### 整合測試
- 測試完整的 PDF → JSON → Neo4j → LLM 流程
- 測試不同案件類型的檢查結果

### UI 測試
- 測試各個按鈕的點擊響應
- 測試錯誤訊息的顯示
- 測試執行緒安全 (不卡 UI)

---

## 依賴版本

詳見 `requirements.txt`:
```
pdfplumber>=0.9.0       # PDF表格提取
PyMuPDF>=1.23.0         # PDF文本提取 (fitz)
neo4j>=5.14.0           # Neo4j Python驅動
openai>=1.10.0          # Azure OpenAI API客戶端
numpy>=1.24.0           # 數值計算
```

Python 版本建議: **3.8+**

---

## 聯絡與貢獻

此專案為內部使用系統，主要用於中興工程契約審查流程。

**維護者**: [您的名稱]
**最後更新**: 2026-01-13
