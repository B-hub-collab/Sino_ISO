import tkinter as tk
from tkinter import messagebox


class ProjectTypeSelector:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("案件類型選擇")
        self.root.geometry("600x450")
        self.root.resizable(False, False)

        # 讓視窗置中
        self.root.eval('tk::PlaceWindow . center')

        # 變數
        self.project_management_checked = tk.BooleanVar(value=False)
        self.design_supervision_checked = tk.BooleanVar(value=True)  # 預設勾選
        self.result = None

        self.create_widgets()

    def create_widgets(self):
        # 主標題
        title_label = tk.Label(self.root, text="請選擇此案件的類型",
                             font=("Arial", 14, "bold"), fg="navy")
        title_label.pack(pady=20)

        # 案件類型選擇框架
        type_frame = tk.LabelFrame(self.root, text="案件類型",
                                  font=("Arial", 12, "bold"), padx=30, pady=20)
        type_frame.pack(pady=10, padx=30, fill="x")

        # 專管選項
        pm_checkbox = tk.Checkbutton(type_frame, text="專管（專案管理）",
                                    variable=self.project_management_checked,
                                    font=("Arial", 11))
        pm_checkbox.pack(anchor="w", pady=5)

        # 設計及監造選項
        ds_checkbox = tk.Checkbutton(type_frame, text="設計及監造",
                                    variable=self.design_supervision_checked,
                                    font=("Arial", 11))
        ds_checkbox.pack(anchor="w", pady=5)

        # 說明文字
        info_text = """處理規則：
• 兩者都勾選：處理所有問題
• 只勾「設計及監造」：跳過專管相關問題
• 只勾「專管」：跳過監造相關問題"""

        info_label = tk.Label(type_frame, text=info_text,
                            font=("Arial", 9), fg="gray", justify="left")
        info_label.pack(anchor="w", pady=(10, 0))

        # 按鈕框架
        button_frame = tk.Frame(self.root)
        button_frame.pack(pady=20)

        # 確認按鈕
        confirm_btn = tk.Button(button_frame, text="確認並繼續",
                              command=self.confirm_selection,
                              font=("Arial", 12, "bold"),
                              bg="#4CAF50", fg="white",
                              padx=20, pady=8)
        confirm_btn.pack(side="left", padx=10)

        # 取消按鈕
        cancel_btn = tk.Button(button_frame, text="取消",
                             command=self.cancel_selection,
                             font=("Arial", 12),
                             bg="#f44336", fg="white",
                             padx=20, pady=8)
        cancel_btn.pack(side="left", padx=10)

    def confirm_selection(self):
        """確認選擇"""
        pm_checked = self.project_management_checked.get()
        ds_checked = self.design_supervision_checked.get()

        if not pm_checked and not ds_checked:
            messagebox.showwarning("警告", "請至少選擇一種案件類型！")
            return

        self.result = {
            'project_management_checked': pm_checked,
            'design_supervision_checked': ds_checked,
            'cancelled': False
        }
        self.root.quit()

    def cancel_selection(self):
        """取消選擇"""
        self.result = {
            'project_management_checked': False,
            'design_supervision_checked': False,
            'cancelled': True
        }
        self.root.quit()

    def get_selection(self):
        """顯示選擇介面並返回結果"""
        # 讓視窗保持在最前面
        self.root.attributes('-topmost', True)
        self.root.focus_force()

        # 執行GUI
        self.root.mainloop()

        # 清理資源
        self.root.destroy()

        return self.result


def show_project_type_selector():
    """顯示案件類型選擇器並返回結果"""
    selector = ProjectTypeSelector()
    return selector.get_selection()


if __name__ == "__main__":
    # 測試用
    result = show_project_type_selector()
    if result:
        print(f"選擇結果: {result}")