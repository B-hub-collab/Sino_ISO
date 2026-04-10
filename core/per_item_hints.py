"""
Per-Item Hints 管理模組
負責讀寫使用者針對特定項次的補充說明
"""

import json
import os
from pathlib import Path


def get_default_hints_path():
    """取得預設的 hints 檔案路徑"""
    import sys

    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        base_dir = Path(sys.executable).parent
    else:
        # Running as script
        base_dir = Path(__file__).parent.parent

    output_dir = base_dir / "output"
    output_dir.mkdir(exist_ok=True)
    return output_dir / "per_item_hints.json"


def load_hints(path=None):
    """
    載入 hints 檔案

    Args:
        path: hints 檔案路徑，若為 None 則使用預設路徑

    Returns:
        dict: key 為項次字串（如 "3.2"），value 為補充說明文字
    """
    if path is None:
        path = get_default_hints_path()

    path = Path(path)

    if not path.exists():
        return {}

    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
            return {}
    except (json.JSONDecodeError, IOError) as e:
        print(f"載入 hints 檔案時發生錯誤: {e}")
        return {}


def save_hints(hints, path=None):
    """
    儲存 hints 到檔案

    Args:
        hints: dict，key 為項次字串，value 為補充說明文字
        path: hints 檔案路徑，若為 None 則使用預設路徑

    Returns:
        bool: 是否儲存成功
    """
    if path is None:
        path = get_default_hints_path()

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(hints, f, ensure_ascii=False, indent=2)
        return True
    except IOError as e:
        print(f"儲存 hints 檔案時發生錯誤: {e}")
        return False


def get_hint(hints, item_number):
    """
    取得特定項次的補充說明

    Args:
        hints: dict，hints 資料
        item_number: str，項次編號（如 "3.2"）

    Returns:
        str: 補充說明文字，若無則返回空字串
    """
    if hints is None:
        return ""
    return hints.get(str(item_number), "")


def set_hint(hints, item_number, text):
    """
    設定特定項次的補充說明

    Args:
        hints: dict，hints 資料（會被修改）
        item_number: str，項次編號（如 "3.2"）
        text: str，補充說明文字

    Returns:
        dict: 更新後的 hints
    """
    if hints is None:
        hints = {}

    item_number = str(item_number)

    if text and text.strip():
        hints[item_number] = text.strip()
    elif item_number in hints:
        del hints[item_number]

    return hints


def delete_hint(hints, item_number):
    """
    刪除特定項次的補充說明

    Args:
        hints: dict，hints 資料（會被修改）
        item_number: str，項次編號（如 "3.2"）

    Returns:
        dict: 更新後的 hints
    """
    if hints is None:
        return {}

    item_number = str(item_number)

    if item_number in hints:
        del hints[item_number]

    return hints


def list_hints(hints):
    """
    列出所有已設定的 hints

    Args:
        hints: dict，hints 資料

    Returns:
        list: 包含 (item_number, text) 的列表，按項次排序
    """
    if hints is None:
        return []
    return [(k, v) for k, v in sorted(hints.items())]
