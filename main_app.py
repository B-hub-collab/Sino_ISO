"""
契約檢查系統 - 主程式 GUI
整合 pdf2json, doc2graph, LLMcheck 三個步驟
"""

import os
import sys
import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
from pathlib import Path


# 設定路徑，讓程式能找到 core 模組
if getattr(sys, 'frozen', False):
    # Running as compiled executable
    BASE_DIR = Path(sys.executable).parent
    RESOURCE_DIR = Path(sys._MEIPASS)
    # 設定 SSL 憑證路徑，確保 neo4j+s:// 等 SSL 連線正常
    os.environ['SSL_CERT_FILE'] = str(RESOURCE_DIR / 'certifi' / 'cacert.pem')
else:
    # Running as script
    BASE_DIR = Path(__file__).parent
    RESOURCE_DIR = BASE_DIR

# 確保 core 模組可以被匯入 (在 resources 中)
CORE_DIR = RESOURCE_DIR / "core"
# 輸出和設定檔應該在執行檔目錄 (在 base 中)
OUTPUT_DIR = BASE_DIR / "output"
sys.path.insert(0, str(CORE_DIR))

# 動態匯入 core 模組
try:
    from core import pdf2json, doc2graph, LLMcheck
    from core.project_type_selector import show_project_type_selector
    from core import per_item_hints
except ImportError:
    import pdf2json
    import doc2graph
    import LLMcheck
    from project_type_selector import show_project_type_selector
    import per_item_hints


class ConfigManager:
    """設定檔管理器"""

    def __init__(self, config_path="config.json"):
        self.config_path = BASE_DIR / config_path
        self.template_path = RESOURCE_DIR / "config.template.json"
        self.config = None

    def load(self):
        """載入設定檔"""
        if not self.config_path.exists():
            return False

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            return True
        except Exception as e:
            messagebox.showerror("設定檔錯誤", f"無法載入設定檔: {e}")
            return False

    def create_from_template(self):
        """從範本建立新設定檔"""
        if not self.template_path.exists():
            messagebox.showerror("錯誤", "找不到 config.template.json")
            return False

        try:
            with open(self.template_path, 'r', encoding='utf-8') as f:
                template = json.load(f)

            # 移除註解欄位
            template.pop('_comment', None)
            template.pop('_note', None)

            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(template, f, ensure_ascii=False, indent=2)

            self.config = template
            return True
        except Exception as e:
            messagebox.showerror("錯誤", f"建立設定檔失敗: {e}")
            return False

    def get(self, *keys, default=None):
        """取得設定值"""
        if not self.config:
            return default

        value = self.config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value


class SetupDialog(tk.Toplevel):
    """首次設定對話框"""

    def __init__(self, parent, config_manager):
        super().__init__(parent)
        self.config_manager = config_manager
        self.result = None

        self.title("首次設定 - 契約檢查系統")
        self.geometry("600x500")
        self.resizable(False, False)

        # 設定為模態視窗
        self.transient(parent)
        self.grab_set()

        self.create_widgets()

        # 置中顯示
        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    def create_widgets(self):
        """建立輸入欄位"""
        main_frame = ttk.Frame(self, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 標題
        title_label = ttk.Label(main_frame, text="請填寫系統設定",
                               font=("Arial", 14, "bold"))
        title_label.pack(pady=(0, 20))

        # Neo4j 設定
        neo4j_frame = ttk.LabelFrame(main_frame, text="Neo4j 資料庫設定", padding=10)
        neo4j_frame.pack(fill=tk.X, pady=5)

        ttk.Label(neo4j_frame, text="URI:").grid(row=0, column=0, sticky=tk.W, pady=3)
        self.neo4j_uri = ttk.Entry(neo4j_frame, width=50)
        self.neo4j_uri.grid(row=0, column=1, pady=3)
        self.neo4j_uri.insert(0, "neo4j+s://")

        ttk.Label(neo4j_frame, text="使用者名稱:").grid(row=1, column=0, sticky=tk.W, pady=3)
        self.neo4j_user = ttk.Entry(neo4j_frame, width=50)
        self.neo4j_user.grid(row=1, column=1, pady=3)
        self.neo4j_user.insert(0, "neo4j")

        ttk.Label(neo4j_frame, text="密碼:").grid(row=2, column=0, sticky=tk.W, pady=3)
        self.neo4j_pass = ttk.Entry(neo4j_frame, width=50, show="*")
        self.neo4j_pass.grid(row=2, column=1, pady=3)

        # Azure OpenAI 設定
        azure_frame = ttk.LabelFrame(main_frame, text="Azure OpenAI 設定", padding=10)
        azure_frame.pack(fill=tk.X, pady=5)

        ttk.Label(azure_frame, text="Endpoint:").grid(row=0, column=0, sticky=tk.W, pady=3)
        self.azure_endpoint = ttk.Entry(azure_frame, width=50)
        self.azure_endpoint.grid(row=0, column=1, pady=3)
        self.azure_endpoint.insert(0, "https://")

        ttk.Label(azure_frame, text="API Key:").grid(row=1, column=0, sticky=tk.W, pady=3)
        self.azure_key = ttk.Entry(azure_frame, width=50, show="*")
        self.azure_key.grid(row=1, column=1, pady=3)

        # 按鈕
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(pady=20)

        ttk.Button(button_frame, text="儲存設定",
                  command=self.save_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="取消",
                  command=self.destroy).pack(side=tk.LEFT, padx=5)

    def save_config(self):
        """儲存設定"""
        # 驗證必填欄位
        if not all([self.neo4j_uri.get().strip(),
                    self.neo4j_pass.get().strip(),
                    self.azure_endpoint.get().strip(),
                    self.azure_key.get().strip()]):
            messagebox.showwarning("警告", "請填寫所有必填欄位")
            return

        # 建立設定字典
        config = {
            "neo4j": {
                "uri": self.neo4j_uri.get().strip(),
                "username": self.neo4j_user.get().strip(),
                "password": self.neo4j_pass.get().strip()
            },
            "azure_openai": {
                "endpoint": self.azure_endpoint.get().strip(),
                "api_key": self.azure_key.get().strip(),
                "api_version": "2025-01-01-preview",
                "deployment_name": "o4-mini"
            },
            "app_settings": {
                "default_output_folder": "output",
                "skip_strikethrough": True,
                "skip_first_page_contract": True,
                "skip_first_page_bidding": False,
                "batch_size_embedding": 10,
                "semantic_search_threshold": 0.5,
                "semantic_search_top_k": 10,
                "hybrid_search_top_k": 25
            },
            "project_types": {
                "available_types": ["project_management", "design_supervision"]
            }
        }

        try:
            with open(self.config_manager.config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)

            self.config_manager.config = config
            self.result = True
            messagebox.showinfo("成功", "設定已儲存")
            self.destroy()
        except Exception as e:
            messagebox.showerror("錯誤", f"儲存設定失敗: {e}")


class ContractCheckerApp:
    """契約檢查系統主視窗"""

    def __init__(self, root):
        self.root = root
        self.root.title("契約檢查系統 v1.0")
        self.root.geometry("900x700")

        # 初始化變數
        self.config_manager = ConfigManager()
        self.checklist_pdf = tk.StringVar()
        self.contract_pdf = tk.StringVar()
        self.bidding_notice_pdf = tk.StringVar()
        self.appendix_a_pdf = tk.StringVar()
        self.checklist_json = tk.StringVar()

        # 確保輸出資料夾存在
        OUTPUT_DIR.mkdir(exist_ok=True)

        # 載入使用者補充說明 (per-item hints)
        self.hints = per_item_hints.load_hints()

        # 檢查並載入設定
        if not self.check_config():
            self.root.destroy()
            return

        self.create_widgets()

    def check_config(self):
        """檢查設定檔"""
        if not self.config_manager.load():
            # 顯示首次設定對話框
            dialog = SetupDialog(self.root, self.config_manager)
            self.root.wait_window(dialog)

            if not dialog.result:
                messagebox.showinfo("取消", "未完成設定，程式結束")
                return False

        return True

    def create_widgets(self):
        """建立GUI元件"""
        # 主容器
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 標題
        title = ttk.Label(main_frame, text="契約檢查系統",
                         font=("Arial", 16, "bold"))
        title.pack(pady=10)

        # 建立分頁
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True, pady=10)

        # 步驟1：上傳測試表單
        tab1 = ttk.Frame(notebook, padding=10)
        notebook.add(tab1, text="步驟1: 測試表單")
        self.create_step1(tab1)

        # 步驟2：上傳契約文件
        tab2 = ttk.Frame(notebook, padding=10)
        notebook.add(tab2, text="步驟2: 契約文件")
        self.create_step2(tab2)

        # 步驟3：執行檢查
        tab3 = ttk.Frame(notebook, padding=10)
        notebook.add(tab3, text="步驟3: 執行檢查")
        self.create_step3(tab3)

        # 狀態列
        self.status_bar = ttk.Label(self.root, text="就緒",
                                    relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)

    def create_step1(self, parent):
        """步驟1: 測試表單PDF轉JSON"""
        frame = ttk.LabelFrame(parent, text="測試表單轉換", padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="請選擇契約審查紀錄表PDF檔案:").pack(anchor=tk.W, pady=5)

        file_frame = ttk.Frame(frame)
        file_frame.pack(fill=tk.X, pady=5)

        ttk.Entry(file_frame, textvariable=self.checklist_pdf,
                 state="readonly").pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(file_frame, text="選擇檔案",
                  command=self.select_checklist_pdf).pack(side=tk.LEFT, padx=5)

        ttk.Button(frame, text="轉換為 JSON",
                  command=self.convert_checklist).pack(pady=10)

        # 結果顯示
        ttk.Label(frame, text="轉換結果:").pack(anchor=tk.W, pady=(10, 0))
        self.step1_result = scrolledtext.ScrolledText(frame, height=15,
                                                      state='disabled')
        self.step1_result.pack(fill=tk.BOTH, expand=True, pady=5)

    def create_step2(self, parent):
        """步驟2: 契約文件上傳到Neo4j"""
        frame = ttk.LabelFrame(parent, text="契約文件上傳", padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        # 契約文件
        ttk.Label(frame, text="契約文件 PDF:").pack(anchor=tk.W, pady=5)
        file_frame1 = ttk.Frame(frame)
        file_frame1.pack(fill=tk.X, pady=5)
        ttk.Entry(file_frame1, textvariable=self.contract_pdf,
                 state="readonly").pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(file_frame1, text="選擇",
                  command=self.select_contract_pdf).pack(side=tk.LEFT, padx=5)

        # 投標須知文件
        ttk.Label(frame, text="投標須知 PDF:").pack(anchor=tk.W, pady=5)
        file_frame2 = ttk.Frame(frame)
        file_frame2.pack(fill=tk.X, pady=5)
        ttk.Entry(file_frame2, textvariable=self.bidding_notice_pdf,
                 state="readonly").pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(file_frame2, text="選擇",
                  command=self.select_bidding_pdf).pack(side=tk.LEFT, padx=5)

        # 附錄A文件（選填）
        ttk.Label(frame, text="投標須知附錄A PDF (選填):").pack(anchor=tk.W, pady=5)
        file_frame3 = ttk.Frame(frame)
        file_frame3.pack(fill=tk.X, pady=5)
        ttk.Entry(file_frame3, textvariable=self.appendix_a_pdf,
                 state="readonly").pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(file_frame3, text="選擇",
                  command=self.select_appendix_pdf).pack(side=tk.LEFT, padx=5)

        # 按鈕區域
        button_frame = ttk.Frame(frame)
        button_frame.pack(pady=10)

        ttk.Button(button_frame, text="上傳至 Neo4j",
                  command=self.upload_documents).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="清空資料庫",
                  command=self.clear_database).pack(side=tk.LEFT, padx=5)

        # 結果顯示
        ttk.Label(frame, text="上傳結果:").pack(anchor=tk.W, pady=(10, 0))
        self.step2_result = scrolledtext.ScrolledText(frame, height=12,
                                                      state='disabled')
        self.step2_result.pack(fill=tk.BOTH, expand=True, pady=5)

    def create_step3(self, parent):
        """步驟3: 執行檢查"""
        frame = ttk.LabelFrame(parent, text="契約檢查", padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="請選擇檢查範圍JSON檔案:").pack(anchor=tk.W, pady=5)

        file_frame = ttk.Frame(frame)
        file_frame.pack(fill=tk.X, pady=5)
        ttk.Entry(file_frame, textvariable=self.checklist_json,
                 state="readonly").pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(file_frame, text="選擇檔案",
                  command=self.select_checklist_json).pack(side=tk.LEFT, padx=5)

        # 項目編號輸入
        item_frame = ttk.Frame(frame)
        item_frame.pack(fill=tk.X, pady=10)

        ttk.Label(item_frame, text="檢查項目編號:").pack(side=tk.LEFT, padx=(0, 5))
        self.item_number_entry = ttk.Entry(item_frame, width=20)
        self.item_number_entry.pack(side=tk.LEFT, padx=5)
        self.item_number_entry.insert(0, "1")
        ttk.Label(item_frame, text="(例如: 1, 1.1, 1.5 等)").pack(side=tk.LEFT, padx=5)

        # 案件類型選擇
        type_frame = ttk.Frame(frame)
        type_frame.pack(fill=tk.X, pady=10)

        self.project_management_var = tk.BooleanVar(value=False)
        self.design_supervision_var = tk.BooleanVar(value=True)

        ttk.Checkbutton(type_frame, text="專案管理",
                       variable=self.project_management_var).pack(side=tk.LEFT, padx=10)
        ttk.Checkbutton(type_frame, text="設計及監造",
                       variable=self.design_supervision_var).pack(side=tk.LEFT, padx=10)

        ttk.Button(frame, text="開始檢查",
                  command=self.start_checking).pack(pady=10)

        # 結果顯示
        ttk.Label(frame, text="檢查結果:").pack(anchor=tk.W, pady=(10, 0))
        self.step3_result = scrolledtext.ScrolledText(frame, height=10,
                                                      state='disabled')
        self.step3_result.pack(fill=tk.BOTH, expand=True, pady=5)

        # === 補充修正區 ===
        hint_frame = ttk.LabelFrame(frame, text="補充修正區 (針對單一項目輸入補充說明)", padding=10)
        hint_frame.pack(fill=tk.X, pady=(10, 5))

        # 項次輸入
        hint_item_frame = ttk.Frame(hint_frame)
        hint_item_frame.pack(fill=tk.X, pady=5)
        ttk.Label(hint_item_frame, text="針對項次:").pack(side=tk.LEFT, padx=(0, 5))
        self.hint_item_entry = ttk.Entry(hint_item_frame, width=15)
        self.hint_item_entry.pack(side=tk.LEFT, padx=5)
        ttk.Label(hint_item_frame, text="(例如: 3.2)").pack(side=tk.LEFT, padx=5)

        # 補充說明輸入
        ttk.Label(hint_frame, text="補充說明:").pack(anchor=tk.W, pady=(5, 0))
        self.hint_text = tk.Text(hint_frame, height=3, wrap=tk.WORD)
        self.hint_text.pack(fill=tk.X, pady=5)

        # 按鈕區
        hint_button_frame = ttk.Frame(hint_frame)
        hint_button_frame.pack(fill=tk.X, pady=5)
        ttk.Button(hint_button_frame, text="儲存補充說明",
                  command=self.save_hint).pack(side=tk.LEFT, padx=5)
        ttk.Button(hint_button_frame, text="重新分析此項目",
                  command=self.reanalyze_with_hint).pack(side=tk.LEFT, padx=5)
        ttk.Button(hint_button_frame, text="清除此項目補充說明",
                  command=self.clear_hint).pack(side=tk.LEFT, padx=5)
        ttk.Button(hint_button_frame, text="查看所有補充說明",
                  command=self.show_all_hints).pack(side=tk.LEFT, padx=5)

    def select_checklist_pdf(self):
        """選擇測試表單PDF"""
        filename = filedialog.askopenfilename(
            title="選擇契約審查紀錄表PDF",
            filetypes=[("PDF檔案", "*.pdf"), ("所有檔案", "*.*")]
        )
        if filename:
            self.checklist_pdf.set(filename)

    def select_contract_pdf(self):
        """選擇契約文件PDF"""
        filename = filedialog.askopenfilename(
            title="選擇契約文件PDF",
            filetypes=[("PDF檔案", "*.pdf"), ("所有檔案", "*.*")]
        )
        if filename:
            self.contract_pdf.set(filename)

    def select_bidding_pdf(self):
        """選擇投標須知PDF"""
        filename = filedialog.askopenfilename(
            title="選擇投標須知PDF",
            filetypes=[("PDF檔案", "*.pdf"), ("所有檔案", "*.*")]
        )
        if filename:
            self.bidding_notice_pdf.set(filename)

    def select_appendix_pdf(self):
        """選擇附錄A PDF"""
        filename = filedialog.askopenfilename(
            title="選擇投標須知附錄A PDF",
            filetypes=[("PDF檔案", "*.pdf"), ("所有檔案", "*.*")]
        )
        if filename:
            self.appendix_a_pdf.set(filename)

    def select_checklist_json(self):
        """選擇檢查清單JSON"""
        filename = filedialog.askopenfilename(
            title="選擇檢查清單JSON",
            filetypes=[("JSON檔案", "*.json"), ("所有檔案", "*.*")]
        )
        if filename:
            self.checklist_json.set(filename)

    def convert_checklist(self):
        """轉換測試表單為JSON"""
        if not self.checklist_pdf.get():
            messagebox.showwarning("警告", "請先選擇PDF檔案")
            return

        def task():
            try:
                self.update_result(self.step1_result, "開始轉換...\n")
                self.status_bar.config(text="正在轉換PDF...")

                # 產生輸出檔名
                pdf_name = Path(self.checklist_pdf.get()).stem
                output_json = OUTPUT_DIR / f"{pdf_name}.json"

                # 執行轉換
                result = pdf2json.pdf_to_hierarchical_json(
                    self.checklist_pdf.get(),
                    str(output_json)
                )

                self.update_result(self.step1_result,
                                 f"轉換完成！\n共處理 {len(result)} 個主項次\n")
                self.update_result(self.step1_result,
                                 f"輸出檔案: {output_json}\n")

                # 自動設定到步驟3
                self.checklist_json.set(str(output_json))

                self.status_bar.config(text="轉換完成")
                messagebox.showinfo("成功", "PDF轉換完成！")

            except Exception as e:
                self.update_result(self.step1_result, f"\n錯誤: {e}\n")
                self.status_bar.config(text="轉換失敗")
                messagebox.showerror("錯誤", f"轉換失敗: {e}")

        threading.Thread(target=task, daemon=True).start()

    def upload_documents(self):
        """上傳文件到Neo4j"""
        if not self.contract_pdf.get() or not self.bidding_notice_pdf.get():
            messagebox.showwarning("警告", "請至少選擇契約文件和投標須知PDF")
            return

        def task():
            try:
                self.update_result(self.step2_result, "開始上傳文件...\n")
                self.status_bar.config(text="正在連接Neo4j...")

                # 建立GraphBuilder實例（使用config的設定）
                neo4j_config = self.config_manager.get("neo4j")

                # 建立doc2graph實例並傳入連線設定
                builder = doc2graph.EnhancedGraphBuilder(
                    neo4j_config["uri"],
                    neo4j_config["username"],
                    neo4j_config["password"]
                )

                skip_strikethrough = self.config_manager.get("app_settings", "skip_strikethrough", default=True)

                # 上傳投標須知文件
                self.update_result(self.step2_result, "\n處理投標須知文件...\n")
                self.status_bar.config(text="處理投標須知...")
                bidding_filename = builder.create_bidding_document(
                    self.bidding_notice_pdf.get(),
                    skip_strikethrough
                )
                self.update_result(self.step2_result,
                                 f"✓ 完成: {bidding_filename}\n")

                # 上傳契約文件
                self.update_result(self.step2_result, "\n處理契約文件...\n")
                self.status_bar.config(text="處理契約文件...")
                contract_clause_count = builder.create_document_and_clauses(
                    self.contract_pdf.get(),
                    skip_strikethrough
                )
                self.update_result(self.step2_result,
                                 f"✓ 完成，建立了 {contract_clause_count} 個條款\n")

                # 上傳附錄A（如果有）
                if self.appendix_a_pdf.get():
                    self.update_result(self.step2_result, "\n處理投標須知附錄A...\n")
                    self.status_bar.config(text="處理附錄A...")
                    appendix_filename = builder.create_appendix_a_document(
                        self.appendix_a_pdf.get(),
                        skip_strikethrough
                    )
                    self.update_result(self.step2_result,
                                     f"✓ 完成: {appendix_filename}\n")

                builder.close()

                self.update_result(self.step2_result, "\n所有文件上傳完成！\n")
                self.status_bar.config(text="上傳完成")
                messagebox.showinfo("成功", "文件上傳完成！")

            except Exception as e:
                import traceback
                error_msg = traceback.format_exc()
                self.update_result(self.step2_result, f"\n錯誤:\n{error_msg}\n")
                self.status_bar.config(text="上傳失敗")
                messagebox.showerror("錯誤", f"上傳失敗: {e}")

        threading.Thread(target=task, daemon=True).start()

    def clear_database(self):
        """清空Neo4j資料庫中的所有資料"""
        # 確認對話框
        confirm = messagebox.askyesno(
            "確認清空資料庫",
            "警告：此操作將刪除資料庫中的所有節點和關係！\n\n您確定要繼續嗎？",
            icon='warning'
        )

        if not confirm:
            return

        def task():
            try:
                self.update_result(self.step2_result, "開始清空資料庫...\n")
                self.status_bar.config(text="正在清空資料庫...")

                # 取得Neo4j設定
                neo4j_config = self.config_manager.get("neo4j")

                # 連接到Neo4j
                from neo4j import GraphDatabase
                driver = GraphDatabase.driver(
                    neo4j_config["uri"],
                    auth=(neo4j_config["username"], neo4j_config["password"])
                )

                with driver.session() as session:
                    # 先查詢總數
                    count_query = "MATCH (n) RETURN count(n) as node_count"
                    result = session.run(count_query)
                    node_count = result.single()['node_count']

                    self.update_result(self.step2_result,
                                     f"資料庫中目前有 {node_count} 個節點\n")

                    if node_count > 0:
                        # 刪除所有節點和關係
                        self.update_result(self.step2_result, "正在刪除所有資料...\n")
                        delete_query = "MATCH (n) DETACH DELETE n"
                        session.run(delete_query)

                        # 確認刪除結果
                        result = session.run(count_query)
                        remaining = result.single()['node_count']

                        if remaining == 0:
                            self.update_result(self.step2_result,
                                             f"✓ 成功刪除 {node_count} 個節點\n")
                            self.update_result(self.step2_result,
                                             "✓ 資料庫已清空\n")
                        else:
                            self.update_result(self.step2_result,
                                             f"⚠ 警告：仍有 {remaining} 個節點未刪除\n")
                    else:
                        self.update_result(self.step2_result, "資料庫已經是空的\n")

                driver.close()

                self.status_bar.config(text="清空完成")
                messagebox.showinfo("完成", "資料庫已清空！")

            except Exception as e:
                import traceback
                error_msg = traceback.format_exc()
                self.update_result(self.step2_result, f"\n錯誤:\n{error_msg}\n")
                self.status_bar.config(text="清空失敗")
                messagebox.showerror("錯誤", f"清空資料庫失敗: {e}")

        threading.Thread(target=task, daemon=True).start()

    def start_checking(self):
        """開始執行檢查"""
        if not self.checklist_json.get():
            messagebox.showwarning("警告", "請先選擇檢查清單JSON檔案")
            return

        # 取得用戶輸入的項目編號
        item_number = self.item_number_entry.get().strip()
        if not item_number:
            messagebox.showwarning("警告", "請輸入檢查項目編號")
            return

        def task():
            try:
                self.update_result(self.step3_result, "初始化檢查系統...\n")
                self.status_bar.config(text="正在初始化...")

                # 取得設定
                neo4j_config = self.config_manager.get("neo4j")
                azure_config = self.config_manager.get("azure_openai")

                # 建立檢查系統
                system = LLMcheck.JSONChecklistQuerySystem(
                    self.checklist_json.get(),
                    azure_config["endpoint"],
                    azure_config["api_key"],
                    neo4j_config["uri"],
                    neo4j_config["username"],
                    neo4j_config["password"]
                )

                # 檢查embedding狀態
                self.update_result(self.step3_result, "檢查embedding狀態...\n")
                with system.driver.session() as session:
                    embedding_count_query = "MATCH (c:Clause) WHERE c.embedding IS NOT NULL RETURN count(c) as count"
                    embedding_result = session.run(embedding_count_query)
                    embedding_count = embedding_result.single()['count']

                    total_count_query = "MATCH (c:Clause) RETURN count(c) as count"
                    total_result = session.run(total_count_query)
                    total_count = total_result.single()['count']

                    self.update_result(self.step3_result,
                                     f"條款總數: {total_count}, 已有embedding: {embedding_count}\n")

                    if embedding_count < total_count:
                        self.update_result(self.step3_result, "開始生成embedding...\n")
                        self.status_bar.config(text="生成embedding...")
                        system.store_embeddings_in_neo4j()

                # 執行檢查
                self.update_result(self.step3_result, f"\n開始檢查項目 {item_number}...\n")
                self.update_result(self.step3_result, "="*60 + "\n")
                self.status_bar.config(text=f"執行檢查項目 {item_number}...")

                result = system.process_item(
                    item_number,
                    deployment_name=azure_config.get("deployment_name", "o4-mini"),
                    project_management_checked=self.project_management_var.get(),
                    design_supervision_checked=self.design_supervision_var.get()
                )

                if result:
                    # 顯示檢查結果
                    self.display_check_result(result)

                system.close()

                self.status_bar.config(text="檢查完成")
                messagebox.showinfo("完成", f"項目 {item_number} 檢查完成！")

            except Exception as e:
                import traceback
                error_msg = traceback.format_exc()
                self.update_result(self.step3_result, f"\n錯誤:\n{error_msg}\n")
                self.status_bar.config(text="檢查失敗")
                messagebox.showerror("錯誤", f"檢查失敗: {e}")

        threading.Thread(target=task, daemon=True).start()

    def display_check_result(self, result):
        """顯示詳細的檢查結果"""
        # 如果是列表結果（包含子項目），遞迴處理每個項目
        if isinstance(result, list):
            for item_result in result:
                self.display_check_result(item_result)
            return

        # 顯示項目編號
        item_number = result.get('item_number', '未知')
        self.update_result(self.step3_result, f"\n檢核項目 {item_number}\n")
        self.update_result(self.step3_result, "="*60 + "\n")

        # 顯示 LLM 分析結果
        analysis = result.get('analysis', '')
        if analysis:
            self.update_result(self.step3_result, "=== LLM分析結果 ===\n")
            self.update_result(self.step3_result, f"{analysis}\n")

        # 顯示相關條款（前3個最相關的）
        related_clauses = result.get('related_clauses', [])
        if related_clauses:
            self.update_result(self.step3_result, "\n=== 相關條款 ===\n")
            for i, clause in enumerate(related_clauses[:3], 1):
                source_name = {
                    'contract': '契約',
                    'bidding_notice': '投標須知',
                    'supplement_notice': '補充投標須知',
                    'appendix_a': '投標須知附錄A'
                }.get(clause.get('source', ''), '相關文件')

                clause_number = clause.get('number', '未知')
                clause_title = clause.get('title', '無標題')

                self.update_result(self.step3_result,
                                 f"{i}. [{source_name}] 第{clause_number}條：{clause_title}\n")

        # 顯示專業審查意見（如果有）
        review_comment = result.get('review_comment', '')
        if review_comment:
            self.update_result(self.step3_result, "\n=== 專業審查意見 ===\n")
            self.update_result(self.step3_result, f"{review_comment}\n")

        self.update_result(self.step3_result, "\n" + "="*60 + "\n")

    def update_result(self, text_widget, message):
        """更新結果顯示"""
        text_widget.config(state='normal')
        text_widget.insert(tk.END, message)
        text_widget.see(tk.END)
        text_widget.config(state='disabled')

    # === 補充修正區相關方法 ===

    def save_hint(self):
        """儲存使用者輸入的補充說明"""
        item_number = self.hint_item_entry.get().strip()
        hint_text = self.hint_text.get("1.0", tk.END).strip()

        if not item_number:
            messagebox.showwarning("警告", "請輸入項次編號")
            return

        if not hint_text:
            messagebox.showwarning("警告", "請輸入補充說明")
            return

        # 更新並儲存 hints
        self.hints = per_item_hints.set_hint(self.hints, item_number, hint_text)
        if per_item_hints.save_hints(self.hints):
            messagebox.showinfo("成功", f"項次 {item_number} 的補充說明已儲存")
        else:
            messagebox.showerror("錯誤", "儲存補充說明失敗")

    def reanalyze_with_hint(self):
        """使用補充說明重新分析項目"""
        item_number = self.hint_item_entry.get().strip()

        if not item_number:
            messagebox.showwarning("警告", "請輸入要重新分析的項次編號")
            return

        if not self.checklist_json.get():
            messagebox.showwarning("警告", "請先選擇檢查清單JSON檔案")
            return

        # 取得此項次的補充說明
        user_hint = per_item_hints.get_hint(self.hints, item_number)

        def task():
            try:
                self.update_result(self.step3_result, f"\n{'='*60}\n")
                self.update_result(self.step3_result, f"重新分析項目 {item_number}...\n")
                if user_hint:
                    self.update_result(self.step3_result, f"使用補充說明: {user_hint[:50]}...\n" if len(user_hint) > 50 else f"使用補充說明: {user_hint}\n")
                self.status_bar.config(text=f"重新分析項目 {item_number}...")

                # 取得設定
                neo4j_config = self.config_manager.get("neo4j")
                azure_config = self.config_manager.get("azure_openai")

                # 建立檢查系統
                system = LLMcheck.JSONChecklistQuerySystem(
                    self.checklist_json.get(),
                    azure_config["endpoint"],
                    azure_config["api_key"],
                    neo4j_config["uri"],
                    neo4j_config["username"],
                    neo4j_config["password"]
                )

                # 執行檢查（帶入 user_hint）
                result = system.process_item(
                    item_number,
                    deployment_name=azure_config.get("deployment_name", "o4-mini"),
                    project_management_checked=self.project_management_var.get(),
                    design_supervision_checked=self.design_supervision_var.get(),
                    user_hint=user_hint
                )

                if result:
                    self.display_check_result(result)

                system.close()

                self.status_bar.config(text="重新分析完成")
                messagebox.showinfo("完成", f"項目 {item_number} 重新分析完成！")

            except Exception as e:
                import traceback
                error_msg = traceback.format_exc()
                self.update_result(self.step3_result, f"\n錯誤:\n{error_msg}\n")
                self.status_bar.config(text="重新分析失敗")
                messagebox.showerror("錯誤", f"重新分析失敗: {e}")

        threading.Thread(target=task, daemon=True).start()

    def clear_hint(self):
        """清除指定項次的補充說明"""
        item_number = self.hint_item_entry.get().strip()

        if not item_number:
            messagebox.showwarning("警告", "請輸入要清除的項次編號")
            return

        # 確認是否有此項次的 hint
        current_hint = per_item_hints.get_hint(self.hints, item_number)
        if not current_hint:
            messagebox.showinfo("提示", f"項次 {item_number} 沒有補充說明")
            return

        # 確認刪除
        if messagebox.askyesno("確認", f"確定要清除項次 {item_number} 的補充說明嗎？"):
            self.hints = per_item_hints.delete_hint(self.hints, item_number)
            if per_item_hints.save_hints(self.hints):
                # 清空輸入框
                self.hint_text.delete("1.0", tk.END)
                messagebox.showinfo("成功", f"項次 {item_number} 的補充說明已清除")
            else:
                messagebox.showerror("錯誤", "清除補充說明失敗")

    def show_all_hints(self):
        """顯示所有已儲存的補充說明"""
        hints_list = per_item_hints.list_hints(self.hints)

        if not hints_list:
            messagebox.showinfo("提示", "目前沒有任何補充說明")
            return

        # 建立顯示視窗
        hint_window = tk.Toplevel(self.root)
        hint_window.title("所有補充說明")
        hint_window.geometry("600x400")

        # 顯示內容
        text_widget = scrolledtext.ScrolledText(hint_window, wrap=tk.WORD)
        text_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        for item_number, hint_text in hints_list:
            text_widget.insert(tk.END, f"項次 {item_number}:\n")
            text_widget.insert(tk.END, f"{hint_text}\n")
            text_widget.insert(tk.END, "-" * 50 + "\n\n")

        text_widget.config(state='disabled')


def main():
    root = tk.Tk()
    app = ContractCheckerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
