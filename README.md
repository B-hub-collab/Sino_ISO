# 契約檢查系統 v1.0

整合式契約審查工具，整合PDF轉JSON、文件上傳Neo4j、AI契約檢查三大功能。

## 📁 資料夾結構

```
contract_checker_app/
├── main_app.py              # 主程式 (GUI介面)
├── config.template.json     # 設定檔範本
├── requirements.txt         # Python套件需求
├── build.spec               # PyInstaller打包設定 (測試後使用)
├── core/                    # 核心模組
│   ├── pdf2json.py         # PDF轉JSON
│   ├── doc2graph.py        # 文件上傳Neo4j
│   ├── LLMcheck.py         # AI契約檢查
│   ├── prompt_templates.py # 提示詞模板
│   └── project_type_selector.py
├── output/                  # 輸出資料夾 (自動建立)
└── docs/                    # 文檔資料夾
```

## 🚀 測試前準備

### 1. 安裝Python套件

```bash
cd contract_checker_app
pip install -r requirements.txt
```

### 2. 準備Neo4j資料庫

確保你有：
- Neo4j雲端實例URL (例如: neo4j+s://xxxxx.databases.neo4j.io)
- 使用者名稱 (通常是 neo4j)
- 密碼

### 3. 準備Azure OpenAI

確保你有：
- Azure OpenAI Endpoint
- API Key
- 部署的模型名稱 (例如: o4-mini)

## ▶️ 執行測試

```bash
cd contract_checker_app
python main_app.py
```

首次執行時，系統會引導你填寫：
- Neo4j連線資訊
- Azure OpenAI設定

這些資訊會儲存在 `config.json` (不會被打包進exe)

## 📝 使用流程

### 步驟1: 測試表單轉換
1. 點選「步驟1: 測試表單」分頁
2. 選擇契約審查紀錄表PDF檔案
3. 點擊「轉換為 JSON」
4. 轉換完成後，JSON會自動存到 `output/` 資料夾

### 步驟2: 契約文件上傳
1. 點選「步驟2: 契約文件」分頁
2. 選擇以下PDF檔案：
   - **契約文件PDF** (必填)
   - **投標須知PDF** (必填)
   - **投標須知附錄A PDF** (選填)
3. 點擊「上傳至 Neo4j」
4. 等待文件解析並上傳到圖資料庫

### 步驟3: 執行檢查
1. 點選「步驟3: 執行檢查」分頁
2. 選擇步驟1產生的JSON檔案
3. 勾選案件類型：
   - ☑ 專案管理
   - ☑ 設計及監造
4. 點擊「開始檢查」
5. 系統會自動：
   - 檢查embedding狀態
   - 如需要則生成語義向量
   - 執行混合搜尋 (關鍵字 + 語義)
   - 生成契約審查報告

## ⚙️ 進階設定

編輯 `config.json` 可調整：

```json
{
  "app_settings": {
    "skip_strikethrough": true,          // 是否跳過刪除線文字
    "skip_first_page_contract": true,    // 契約文件跳過首頁
    "skip_first_page_bidding": false,    // 投標須知跳過首頁
    "batch_size_embedding": 10,          // Embedding批次大小
    "semantic_search_threshold": 0.5,    // 語義搜尋閾值
    "semantic_search_top_k": 10,         // 語義搜尋結果數
    "hybrid_search_top_k": 25            // 混合搜尋結果數
  }
}
```

## 🧪 測試重點

請測試以下場景：

### ✅ 基本功能測試
- [ ] 首次執行時設定對話框是否正常
- [ ] 步驟1: PDF轉JSON是否成功
- [ ] 步驟2: 三種文件上傳是否正常
- [ ] 步驟3: 檢查流程是否完整執行

### ✅ 錯誤處理測試
- [ ] 未選擇檔案時點擊按鈕 → 應顯示警告
- [ ] 錯誤的Neo4j連線資訊 → 應顯示錯誤訊息
- [ ] 錯誤的Azure API Key → 應顯示錯誤訊息
- [ ] 選擇非PDF檔案 → 應正常處理或提示

### ✅ 介面測試
- [ ] 多個分頁切換是否順暢
- [ ] 長時間操作時介面是否卡住 (已用threading處理)
- [ ] 結果視窗文字是否正確顯示中文

## 🐛 常見問題

### Q: 執行時顯示 "No module named 'core'"
**A:** 確保在 `contract_checker_app/` 資料夾內執行 `python main_app.py`

### Q: PDF轉換失敗
**A:**
- 確認PDF檔案是否損壞
- 確認pdfplumber套件是否正確安裝
- 查看錯誤訊息詳細內容

### Q: 無法連接Neo4j
**A:**
- 確認網路連線正常
- 確認URI格式正確 (neo4j+s://...)
- 確認密碼正確
- 檢查Neo4j實例是否已啟動

### Q: Azure OpenAI呼叫失敗
**A:**
- 確認API Key有效
- 確認Endpoint URL正確
- 確認有足夠的配額
- 檢查模型部署名稱

## 📦 測試完成後打包

測試確認沒問題後，執行：

```bash
# Windows
build.bat

# 或手動執行
pyinstaller build.spec --clean
```

打包完成後，可執行檔位於：
```
dist/契約檢查系統/契約檢查系統.exe
```

將整個 `dist/契約檢查系統/` 資料夾複製給使用者即可。

## 🔒 安全提醒

- **不要將 config.json 加入版控**
- **不要將含有密碼的config.json分享給他人**
- **建議使用環境變數管理敏感資訊** (未來版本可改進)

## 📞 支援

如有問題，請聯繫開發團隊。

---

**版本:** 1.0
**更新日期:** 2026-01-07
