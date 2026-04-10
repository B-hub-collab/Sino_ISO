import json
import re
import pdfplumber


def pdf_to_hierarchical_json(pdf_file_path, output_json_path=None):
    """
    處理 PDF 格式的文件，跳過第一頁，從第二頁開始提取表格轉換成階層 JSON
    """

    result = []
    current_main_item = None
    current_sub_item = None

    try:
        with pdfplumber.open(pdf_file_path) as pdf:
            print(f"PDF 共有 {len(pdf.pages)} 頁")

            # 跳過第一頁，從第二頁開始處理
            for page_num in range(1, len(pdf.pages)):  # 索引1開始，跳過第0頁
                page = pdf.pages[page_num]
                print(f"\n處理第 {page_num + 1} 頁...")

                # 提取表格
                tables = page.extract_tables()

                if not tables:
                    print(f"  第 {page_num + 1} 頁沒有找到表格")
                    continue

                print(f"  找到 {len(tables)} 個表格")

                # 處理每個表格
                for table_idx, table in enumerate(tables):
                    print(f"  處理表格 {table_idx + 1}，共 {len(table)} 行")

                    for row_idx, row in enumerate(table):
                        # 跳過標題行（通常第一行是標題）
                        if row_idx == 0 and row and row[0] == "項次":
                            continue

                        # 確保行有足夠的欄位
                        if not row or len(row) < 4:
                            continue

                        # 提取欄位值（處理 None 值）
                        item_number_text = (row[0] or "").strip()
                        check_item = (row[1] or "").strip()
                        clause = (row[2] or "").strip()
                        clause_summary = (row[3] or "").strip()
                        note = (row[4] or "").strip() if len(row) > 4 else ""

                        # 跳過空行
                        if not item_number_text and not check_item and not clause_summary and not note:
                            continue

                        # 處理項次
                        item_number = parse_item_number(item_number_text)

                        # 主項次（純整數，如 1, 2, 3）
                        if item_number and item_number[0] == 'main':
                            current_main_item = {
                                "主項次": item_number[1],
                                "主項說明": check_item,
                                "備註": note,
                                "子項目": []
                            }
                            result.append(current_main_item)
                            current_sub_item = None

                        # 子項目（整數.整數，如 1.1, 1.10, 2.3）
                        elif item_number and item_number[0] == 'sub':
                            if current_main_item:
                                current_sub_item = {
                                    "項次": item_number[1],  # 保留原始字串，不做 float 轉換
                                    "檢查項目": check_item,
                                    "條款": clause,
                                    "條款摘要": clause_summary,
                                    "備註": note,
                                    "子項目": []
                                }
                                current_main_item["子項目"].append(current_sub_item)

                        # 子子項目（字母，如 a, b, c）
                        elif item_number_text and re.match(r'^[a-z]\.?$', item_number_text, re.IGNORECASE):
                            if current_sub_item:
                                letter = item_number_text.replace('.', '').lower()
                                sub_sub_item = {
                                    "項次": f"{current_sub_item['項次']}.{letter}",
                                    "檢查項目": check_item,
                                    "條款": clause,
                                    "條款摘要": clause_summary,
                                    "備註": note
                                }
                                current_sub_item["子項目"].append(sub_sub_item)

                        # 補充說明（沒有項次但有條款摘要或其他內容）
                        elif not item_number_text and (clause_summary or check_item or note):
                            if current_sub_item and current_sub_item["子項目"]:
                                last_sub_sub_item = current_sub_item["子項目"][-1]
                                if check_item:
                                    last_sub_sub_item["檢查項目"] = (last_sub_sub_item.get("檢查項目", "") + "\n" + check_item).strip()
                                if clause_summary:
                                    last_sub_sub_item["條款摘要"] = (last_sub_sub_item.get("條款摘要", "") + "\n" + clause_summary).strip()
                                if note:
                                    last_sub_sub_item["備註"] = (last_sub_sub_item.get("備註", "") + "\n" + note).strip()
                            elif current_sub_item:
                                if check_item:
                                    current_sub_item["檢查項目"] = (current_sub_item.get("檢查項目", "") + "\n" + check_item).strip()
                                if clause_summary:
                                    current_sub_item["條款摘要"] = (current_sub_item.get("條款摘要", "") + "\n" + clause_summary).strip()
                                if note:
                                    current_sub_item["備註"] = (current_sub_item.get("備註", "") + "\n" + note).strip()
                            elif current_main_item and current_main_item["子項目"]:
                                last_sub_item = current_main_item["子項目"][-1]
                                if check_item:
                                    last_sub_item["檢查項目"] = (last_sub_item.get("檢查項目", "") + "\n" + check_item).strip()
                                if clause_summary:
                                    last_sub_item["條款摘要"] = (last_sub_item.get("條款摘要", "") + "\n" + clause_summary).strip()
                                if note:
                                    last_sub_item["備註"] = (last_sub_item.get("備註", "") + "\n" + note).strip()

    except Exception as e:
        print(f"處理 PDF 時發生錯誤: {e}")
        import traceback
        traceback.print_exc()

    # 輸出 JSON
    if output_json_path:
        with open(output_json_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\nJSON檔案已保存至: {output_json_path}")

    return result


def parse_item_number(text):
    """
    解析項次文字，返回 (種類, 原始文字) 的 tuple：
      - ('main', '1')      → 主項次（純整數，無小數點）
      - ('sub', '1.10')    → 子項目（整數.整數，保留原始字串）
      - None               → 無法識別
    注意：不使用 float() 轉換，避免 "1.10" 變成 "1.1"。
    """
    if not text:
        return None

    # 移除結尾點號，如 "1." -> "1"
    clean_text = text.rstrip('.')

    # 主項次：純整數
    if re.match(r'^\d+$', clean_text):
        return ('main', clean_text)

    # 子項目：「整數.整數」格式，如 "1.10", "2.3"
    if re.match(r'^\d+\.\d+$', clean_text):
        return ('sub', clean_text)

    return None


if __name__ == "__main__":
    # 使用範例
    pdf_file = r"C:\Users\user\Desktop\中興ISO案\BD03標_契約書(投標前)審查紀錄表-更正公告版-業務部(等級B)__增列職安項目(1141203)_info.docx 的副本.docx.pdf"
    json_file = "pdf_output.json"

    hierarchical_data = pdf_to_hierarchical_json(pdf_file, json_file)
    print(f"\n共處理了 {len(hierarchical_data)} 個主項次")
