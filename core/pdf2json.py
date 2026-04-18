import json
import re
import pdfplumber


def find_column_indices(header_row):
    """
    根據標題行找出各欄位的索引位置
    返回: {'item_num': idx, 'check_item': idx, 'clause': idx, 'summary': idx, 'note': idx}
    或 None (如果不是標題行)
    """
    indices = {}

    for idx, cell in enumerate(header_row):
        if not cell:
            continue
        cell_text = cell.strip()

        if '項次' in cell_text:
            indices['item_num'] = idx
        elif '檢查項目' in cell_text:
            indices['check_item'] = idx
        elif '條款摘要' in cell_text:
            indices['summary'] = idx
        elif '條款' in cell_text and '摘要' not in cell_text:
            indices['clause'] = idx
        elif '備註' in cell_text:
            indices['note'] = idx

    # 至少需要找到項次和檢查項目
    if 'item_num' in indices and 'check_item' in indices:
        return indices
    return None


def get_column_ranges(indices):
    """計算每個欄位的起始和結束索引"""
    sorted_items = sorted(indices.items(), key=lambda x: x[1])
    ranges = {}

    for i, (name, start_idx) in enumerate(sorted_items):
        if i + 1 < len(sorted_items):
            end_idx = sorted_items[i + 1][1]
        else:
            end_idx = None  # 最後一個欄位到行尾
        ranges[name] = (start_idx, end_idx)

    return ranges


def extract_cell_value(row, start_idx, next_idx=None):
    """
    從 start_idx 開始提取值，合併到下一個欄位之前的所有非空內容
    """
    if start_idx >= len(row):
        return ""

    # 如果有明確的下一個欄位索引，只取這個範圍
    end_idx = next_idx if next_idx else len(row)

    # 合併這個範圍內的所有非空值
    values = []
    for idx in range(start_idx, min(end_idx, len(row))):
        if row[idx]:
            val = row[idx].strip()
            if val:
                values.append(val)

    return ' '.join(values) if values else ""


def pdf_to_hierarchical_json(pdf_file_path, output_json_path=None):
    """
    處理 PDF 格式的文件，自動偵測表格起始頁和欄位位置
    """

    result = []
    current_main_item = None
    current_sub_item = None
    column_indices = None  # 欄位索引映射
    column_ranges = None   # 欄位範圍
    seen_main_numbers = set()  # 已見過的主項次編號

    try:
        with pdfplumber.open(pdf_file_path) as pdf:
            print(f"PDF 共有 {len(pdf.pages)} 頁")

            # 掃描所有頁面，自動尋找表格起始頁
            for page_num in range(len(pdf.pages)):
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
                        # 尚未找到標題行，嘗試偵測
                        if column_indices is None:
                            detected = find_column_indices(row)
                            if detected:
                                column_indices = detected
                                column_ranges = get_column_ranges(detected)
                                print(f"在第 {page_num + 1} 頁找到標題行，欄位映射: {column_indices}")
                                continue  # 跳過標題行本身

                        # 已有欄位映射，解析資料行
                        if column_indices:
                            # 確保行有資料
                            if not row:
                                continue

                            # 使用偵測到的索引提取欄位值
                            # 注意：由於階層結構（縮排），子項目的所有欄位會向左偏移1-2個位置
                            # 因此對每個欄位都需要檢查多個可能的索引
                            base_check_item_idx = column_indices.get('check_item', 4)
                            base_clause_idx = column_indices.get('clause', 7)
                            base_summary_idx = column_indices.get('summary', 10)
                            base_note_idx = column_indices.get('note', 13)

                            # 項次：檢查索引0到檢查項目欄位之前的所有位置
                            item_number_text = ""
                            for idx in range(0, base_check_item_idx):
                                val = extract_cell_value(row, idx, idx + 1)
                                if val:
                                    item_number_text = val
                                    break

                            # 檢查項目：嘗試基準索引及其左邊的位置
                            check_item = ""
                            for offset in [0, -1, -2]:
                                idx = base_check_item_idx + offset
                                if idx >= 0:
                                    val = extract_cell_value(row, idx, idx + 1)
                                    if val:
                                        check_item = val
                                        break

                            # 條款：嘗試基準索引及其左邊的位置
                            clause = ""
                            if 'clause' in column_indices:
                                for offset in [0, -1, -2]:
                                    idx = base_clause_idx + offset
                                    if idx >= 0:
                                        val = extract_cell_value(row, idx, idx + 1)
                                        if val:
                                            clause = val
                                            break

                            # 條款摘要：嘗試基準索引及其左邊的位置
                            clause_summary = ""
                            if 'summary' in column_indices:
                                for offset in [0, -1, -2]:
                                    idx = base_summary_idx + offset
                                    if idx >= 0:
                                        val = extract_cell_value(row, idx, idx + 1)
                                        if val:
                                            clause_summary = val
                                            break

                            # 備註：嘗試基準索引及其左邊的位置
                            note = ""
                            if 'note' in column_indices:
                                for offset in [0, -1, -2]:
                                    idx = base_note_idx + offset
                                    if idx >= 0:
                                        val = extract_cell_value(row, idx, idx + 1)
                                        if val:
                                            note = val
                                            break

                            # 跳過空行
                            if not item_number_text and not check_item and not clause_summary and not note:
                                continue

                            # 跳過非項次的行（如「案件類型」等元數據行）
                            # 這些行的特徵是：有項次文字但無法解析為數字，且檢查項目為空
                            if item_number_text and not parse_item_number(item_number_text) and not check_item:
                                continue

                            # 處理項次
                            item_number = parse_item_number(item_number_text)

                            # 主項次（純整數，如 1, 2, 3）
                            if item_number and item_number[0] == 'main':
                                main_num = item_number[1]

                                # 處理重複編號：如果是 "1" 且已見過，推斷為下一個編號
                                if main_num in seen_main_numbers:
                                    # 找出當前最大的主項次編號
                                    max_num = max([int(item["主項次"]) for item in result], default=0)
                                    main_num = str(max_num + 1)
                                    print(f"    [推斷] 項次 '{item_number[1]}' 已存在，推斷為主項次 {main_num}")

                                seen_main_numbers.add(main_num)

                                current_main_item = {
                                    "主項次": main_num,
                                    "主項說明": check_item,
                                    "備註": note,
                                    "子項目": []
                                }
                                result.append(current_main_item)
                                current_sub_item = None

                            # 子項目（整數.整數，如 1.1, 1.10, 2.3）
                            elif item_number and item_number[0] == 'sub':
                                # 提取主項次編號 (例如 "10.1" → "10")
                                sub_number = item_number[1]
                                main_number = sub_number.split('.')[0]

                                # 檢查當前主項次是否匹配
                                if not current_main_item or current_main_item["主項次"] != main_number:
                                    # 不匹配或不存在，自動創建主項次
                                    seen_main_numbers.add(main_number)
                                    current_main_item = {
                                        "主項次": main_number,
                                        "主項說明": "",  # 沒有明確的主項說明
                                        "備註": "",
                                        "子項目": []
                                    }
                                    result.append(current_main_item)
                                    current_sub_item = None

                                # 添加子項目
                                current_sub_item = {
                                    "項次": sub_number,  # 保留原始字串，不做 float 轉換
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
    import sys

    # 測試新格式 PDF
    if len(sys.argv) > 1 and sys.argv[1] == "--old":
        # 測試舊格式（向後相容性測試）
        pdf_file = r"D:\Download\BD03標_契約書(投標前)審查紀錄表-更正公告版-業務部(等級B)__增列職安項目(1141203)_info.docx 的副本.docx.pdf"
        json_file = "pdf_output_old_test.json"
    else:
        # 預設測試新格式
        pdf_file = r"C:\Users\user\Desktop\中興ISO案\02_BD03標_契約書(投標前)審查紀錄表-更正公告版-業務部(等級B)_增列錯誤樣態_空白格式(1150414).pdf"
        json_file = "pdf_output_new.json"

    hierarchical_data = pdf_to_hierarchical_json(pdf_file, json_file)
    total_sub = sum(len(item["子項目"]) for item in hierarchical_data)
    print(f"\n共處理了 {len(hierarchical_data)} 個主項次，{total_sub} 個子項目")
