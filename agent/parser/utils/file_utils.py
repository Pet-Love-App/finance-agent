"""
agent/parser/utils/file_utils.py
"""
from pathlib import Path
from typing import Optional
import re


def detect_encoding(file_path: str) -> str:
    """检测文件编码"""
    try:
        import chardet
        with open(file_path, "rb") as f:
            raw = f.read(10000)
        result = chardet.detect(raw)
        return result.get("encoding", "utf-8") or "utf-8"
    except ImportError:
        return "utf-8"


def excel_col_letter(col_idx: int) -> str:
    """0-based column index → Excel 列字母 (0→A, 25→Z, 26→AA)"""
    result = ""
    idx = col_idx
    while True:
        result = chr(idx % 26 + ord('A')) + result
        idx = idx // 26 - 1
        if idx < 0:
            break
    return result


def excel_a1(row_idx: int, col_idx: int) -> str:
    """0-based (row, col) → Excel A1 格式"""
    return f"{excel_col_letter(col_idx)}{row_idx + 1}"


def excel_range(r1: int, c1: int, r2: int, c2: int) -> str:
    """0-based corners → Excel range"""
    return f"{excel_a1(r1, c1)}:{excel_a1(r2, c2)}"


def sanitize_filename(name: str) -> str:
    """去除文件名中不合法字符"""
    return re.sub(r'[<>:"/\\|?*]', '_', name).strip()