def should_skip_item(check_item, project_management_checked=False, design_supervision_checked=True):
    """
    判斷是否應跳過某個檢查項目

    Args:
        check_item (str): 檢查項目
        project_management_checked (bool): 是否勾選專管
        design_supervision_checked (bool): 是否勾選設計及監造

    Returns:
        bool: True 表示應跳過此項目
    """
    has_project_management = "專管" in check_item
    has_supervision = "監造" in check_item

    # 特殊處理：如果同時包含專管和監造（如「專管/監造」、「監造/專管」），永遠不跳過
    if has_project_management and has_supervision:
        return False

    # 如果兩者都勾選，不跳過任何項目
    if project_management_checked and design_supervision_checked:
        return False

    # 如果只勾選設計及監造，跳過純專管項目
    if design_supervision_checked and not project_management_checked:
        return has_project_management and not has_supervision

    # 如果只勾選專管，跳過純監造項目
    if project_management_checked and not design_supervision_checked:
        return has_supervision and not has_project_management

    # 如果都沒勾選，跳過所有項目
    return True


def get_contract_analysis_prompt(main_description, parent_item, check_item, current_summary, clauses_text,
                                project_management_checked=False, design_supervision_checked=True,
                                user_hint=""):
    """
    生成契約分析的 prompt

    Args:
        main_description (str): 主項說明
        parent_item (str): 父項目檢查項目
        check_item (str): 檢查項目
        current_summary (str): 當前項目的條款摘要格式
        clauses_text (str): 相關條款文本
        project_management_checked (bool): 是否勾選專管
        design_supervision_checked (bool): 是否勾選設計及監造

    Returns:
        str: 格式化的 prompt，如果應跳過則返回特殊標記
    """
    # 檢查是否應跳過此項目
    if should_skip_item(check_item, project_management_checked, design_supervision_checked):
        return "SKIP_ITEM"
    # 生成案件類型說明
    project_type_display = []
    if project_management_checked:
        project_type_display.append("■專管")
    else:
        project_type_display.append("□專管")

    if design_supervision_checked:
        project_type_display.append("■設計及監造")
    else:
        project_type_display.append("□設計及監造")

    project_type_text = " ".join(project_type_display)

    # 組織層次信息顯示
    hierarchy_info = f"主項說明：{main_description}"
    if parent_item:
        hierarchy_info += f"\n            父項目：{parent_item}"
    hierarchy_info += f"\n            檢查項目：{check_item}"

    prompt = f"""你是一個專業的工程契約檢核專家。請根據以下招標文件條款，分析檢核項目並填寫相關資訊。

            **案件類型選擇：{project_type_text}**

            **檢核項目層次結構：**
            {hierarchy_info}

            **當前項目的條款摘要格式（必須完全按照此格式回答）**：{current_summary}

            **重要約束**：請理解這是「{main_description}」主項下{"的「" + parent_item + "」" if parent_item else ""}的檢核項目，只在此主題相關的條款中尋找答案，不要被其他主題的類似內容誤導。

            相關條款：
            {clauses_text}

            **重要限制：你只能引用上方「相關條款」區塊中明確列出的條款。嚴禁引用任何未在上方列出的條款編號，即使你可能知道該條款存在。如果上方條款中沒有找到相關資訊，請在「條款」欄位填寫空字串。**

            **嚴格按照以下格式回答，不可偏離**：
            條款：[只能填寫上方「相關條款」中列出的具體條款編號，如「第X條」或「投標須知第XX條」。若上方條款均無相關資訊，請填寫空字串""]
            條款摘要：[必須100%按照上方「當前項目的條款摘要格式」，不可使用任何其他項目的格式]
            分析說明：[簡述判斷依據，必須引用上方條款中的具體文字作為依據]

            **強制推理步驟**（在回答前必須完成）：
            1. 先找出條款中與檢查項目直接相關的關鍵句子
            2. 逐字分析該句子的主詞、受詞、動詞，確認「誰負擔」「誰辦理」「誰負責」
            3. 特別注意否定句：「不得」「不應」「免除」等詞會反轉意思
            4. 確認你的理解與條款原文邏輯一致後，再填寫條款摘要

            **絕對禁止的行為**：
            1. 創造原格式中沒有的任何選項、文字或結構
            2. 使用其他檢核項目的條款摘要格式
            3. 修改原格式的基本結構或選項內容
            4. 添加原格式中不存在的checkbox或選項

            **唯一允許的修改**：
            1. 將□改為■（勾選）
            2. 在現有的()內填入內容
            3. 完全不修改（保持原狀）

            **勾選優先級規則**：
            - 當條款摘要格式中有多個checkbox選項時，應優先勾選「最具體、最精確匹配」的選項
            - 如果條款內容明確提到某個具體險種/項目名稱，且該名稱正好是checkbox中的一個選項，應直接勾選該具體選項，而非「其他」
            - 「其他」選項只有在條款內容確實不屬於任何已列出的具體選項時才勾選
            - 範例：條款寫「其他：第三人意外責任險」，checkbox選項有「□第三人意外責任險□其他」→ 應勾選「■第三人意外責任險」，因為該險種已是明確的選項，不應歸入「其他」

            **關鍵判斷原則**：
            - **結構存在 ≠ 內容存在**：條文中有某個項目的標題或框架，但實際未填寫內容，應判斷為「無」
            - **空白、未填寫、待填 = 無**：看到空白欄位、未填寫內容、「無者免填」等，都表示該項目不存在
            - **重點看實際內容，不要被條文結構誤導**

            **案件類型處理規則**：
            - 案件類型設定：{project_type_text}
            - 若只選擇「設計及監造」：僅處理監造相關問題，跳過專管問題
            - 若只選擇「專管」：僅處理專管相關問題，跳過監造問題
            - 若兩者都選擇：處理所有問題

            **條款摘要填寫規則**：
            - 當前格式：『{current_summary}』
            - 只能修改此格式中的□為■，或在()內填入內容
            - 絕對不可創造新的選項或使用其他項目的格式
            - 如果找不到明確依據，就保持原格式不變

            **特別注意**：
            - 不要被相關條款內容誘導而創造新格式
            - 請考慮所有提供的內容並再給出結論
            - 不要使用計價方式、給付方式等其他項目的選項
            - 嚴格按照當前項目『{current_summary}』的結構回答
            **格式檢查**：在回答前，請確認條款摘要部分是否完全符合『{current_summary}』的結構

            **補充說明**:
            - 條款提到「每一個月計價」、「每月估驗」、「按月給付」、「以每一個月為一期」等，應進行勾選，並且如果有括號的話應在括號內填入「1」
            - 條款提到其他計價週期，如「每季」則填入「3」，「每半年」則填入「6」
            -「■施工進度」vs「■監造進度」區分：
                - 條款提到「按實際施工進度百分比計付」→ 勾選「■施工進度」
                - 條款提到「按監造工作完成進度計付」→ 勾選「■監造進度」
                - 「監造服務費按施工進度計價」→ 只勾選「■施工進度」，不勾選「■監造進度」

            **格式解讀規則**（針對條款中有空白或特殊格式的情況）:
            - 「百分之 X 或 Y 倍」這種格式，應選擇有明確填寫的數值
            - 若看到「1 倍」、「1倍」字樣，即使前面有空白或底線，也應判斷為「1倍」並勾選
            - 條款中出現「百分之___或 1 倍」，應解讀為「1倍」（選擇有填寫的選項）
            - 不要因為格式中有空白就判斷為「未載明」，要看實際有填寫數值的部分

            **後續擴充判斷邏輯**（針對「□無□有(NTD       )」格式）:
            - **關鍵判斷標準**：看條文「冒號後」或「括號後」是否有填寫實際內容
            - 條款範例：「本採購保留未來向得標廠商增購之權利，擬增購之項目及內容(請載明擴充之金額、數量或期間上限)：______」
              → 冒號後是空白、底線或未填寫 → 判斷為「■無□有」
            - **有條文結構 ≠ 有實際內容**：即使條文提到「保留增購權利」的文字，但若**未明確填寫具體金額、數量或項目**，仍應判斷為「■無□有」
            - **只有以下情況才判斷為「有」**：條款中冒號或括號後**明確載明具體的擴充金額、數量或期間上限**（如「NTD 1,000,000元」、「數量100件」、「期間1年」等），才勾選「□無■有」並在括號內填入金額
            - **「未保留增購權利者免填」且實際未填寫** = 「無」
            - **「保留權利但未實際填寫內容」** = 「無後續擴充」

            **甲方辦理事項判斷邏輯**（針對「□無□有」格式）:
            - 條款中如有「甲方辦理事項」、「甲方工作項目」等標題或結構，但**內容空白未填寫**，應判斷為「■無□有」
            - 條款註明「無者免填」、「無則免填」等，且實際**未填寫任何內容**，表示「無」
            - 只有當條款中**明確列出具體的甲方辦理事項內容**時，才勾選「□無■有」
            - **不要被條文結構存在誤導，重點是實際內容是否填寫**
            
            **保險條款判斷邏輯**（針對保險金額及自負額等項目）:
            - 檢查項目9.2.a「保險金額及自負額」格式：「每一事故：    ，累計：     自負額：          」

            **重要判斷原則**：
            - 當檢查項目屬於「專責險保險條件」時，只關注專業責任險相關條款
            - 嚴格根據找到的條款內容填寫，不要臆測或混淆
            - 不同保險類型有不同的保險金額規定，必須精確識別


            **檢核重點**：
            - 根據檢查項目的保險類型，在條款中找到對應的保險金額規定
            - 如果條款中同時出現多種保險，只提取與檢查項目相符的保險類型內容
            - 嚴格按照條款原文填寫，保持用詞一致
            """

    # 注入使用者補充說明（如果有）
    if user_hint and user_hint.strip():
        prompt += f"""

            ============================================
            **【重要】使用者補充說明（必須遵守）**：
            {user_hint.strip()}

            請根據上述補充說明調整你的判斷結果。
            ============================================
            """

    return prompt


def get_keyword_extraction_prompt(main_description, check_item):
    """
    生成關鍵字提取的 prompt

    Args:
        main_description (str): 主項說明
        check_item (str): 檢查項目

    Returns:
        str: 格式化的 prompt
    """
    prompt = f"""你是專業的契約分析專家。請分析以下檢核項目，提取出在招標文件中搜尋時最有效的關鍵字。

        主項說明：{main_description}
        檢查項目：{check_item}

        請提取3-5個最重要的關鍵字，這些關鍵字應該能在契約條款中找到相關內容。

        要求：
        1. 只輸出關鍵字，用逗號分隔
        2. 不要解釋，不要其他文字
        3. 關鍵字要具體且容易在契約中匹配
        4. 優先從檢查項目中提取，補充主項說明的關鍵字

        範例：
        輸入：主項說明：計畫內容概要，檢查項目：業務類別
        輸出：業務類別,業務,類別,計畫內容

        關鍵字："""

    return prompt


def get_keyword_extraction_hierarchy_prompt(main_description, parent_item, check_item):
    """
    生成考慮層次結構的關鍵字提取 prompt

    Args:
        main_description (str): 主項說明
        parent_item (str): 父項目檢查項目
        check_item (str): 當前檢查項目

    Returns:
        str: 格式化的 prompt
    """
    if parent_item:
        prompt = f"""你是專業的契約分析專家。請分析以下多層次檢核項目，提取出在招標文件中搜尋時最有效的關鍵字。

            主項說明：{main_description}
            父項目：{parent_item}
            檢查項目：{check_item}

            請提取6-8個關鍵字，同時包含特異性關鍵字（避免混淆）和通用關鍵字（擴大搜尋範圍）。

            **雙層關鍵字策略**：
            1. **特異性關鍵字**（3-4個）：結合主項+父項目+檢查項目，創造精確的組合詞
            2. **通用關鍵字**（3-4個）：從檢查項目中提取基本詞彙，不加主題前綴

            **提取原則**：
            1. 父項目提供重要的限定條件，不可忽略
            2. 特異性關鍵字防止跨主題混淆
            3. 通用關鍵字確保不錯過使用簡單表達的條款

            要求：
            1. 只輸出關鍵字，用逗號分隔
            2. 不要解釋，不要其他文字
            3. 先列特異性關鍵字，再列通用關鍵字

            範例：
            輸入：主項說明：保險，父項目：專責險保險條件，檢查項目：保險金額及自負額
            輸出：專責險,專業責任險,保險金額,自負額,保險條件,金額,責任險

            關鍵字："""
    else:
        # 如果沒有父項目，也使用雙層關鍵字策略
        prompt = f"""你是專業的契約分析專家。請分析以下檢核項目，提取出在招標文件中搜尋時最有效的關鍵字。

            主項說明：{main_description}
            檢查項目：{check_item}

            請提取5-7個關鍵字，同時包含特異性關鍵字（避免混淆）和通用關鍵字（擴大搜尋範圍）。

            **雙層關鍵字策略**：
            1. **特異性關鍵字**（2-3個）：結合主項+檢查項目，創造精確的組合詞
            2. **通用關鍵字**（3-4個）：從檢查項目中提取基本詞彙，不加主題前綴

            **提取原則**：
            1. 特異性關鍵字防止跨主題混淆
            2. 通用關鍵字確保不錯過使用簡單表達的條款
            3. 主項說明提供重要的主題約束

            要求：
            1. 只輸出關鍵字，用逗號分隔
            2. 不要解釋，不要其他文字
            3. 先列特異性關鍵字，再列通用關鍵字

            範例：
            輸入：主項說明：保險，檢查項目：提送期限
            輸出：保險提送期限,保險文件提交,提送期限,期限,提交

            關鍵字："""

    return prompt