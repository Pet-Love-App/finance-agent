from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from agent.tools.base import ToolResult, fail, ok


SUPPORTED_EXTS = {
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".tif",
    ".tiff",
    ".docx",
    ".xlsx",
    ".xls",
    ".txt",
    ".md",
}


def scan_inputs(paths: List[str]) -> ToolResult:
    if not paths:
        return fail("未提供输入路径")

    collected: List[str] = []
    for item in paths:
        path = Path(item)
        if not path.exists():
            continue
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTS:
            collected.append(str(path.resolve()))
            continue
        if path.is_dir():
            for file_path in path.rglob("*"):
                if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_EXTS:
                    collected.append(str(file_path.resolve()))

    if not collected:
        return fail("未扫描到可处理文件")
    return ok(files=sorted(set(collected)))


def classify_files(files: List[str]) -> ToolResult:
    groups: Dict[str, List[str]] = {
        "pdf": [],
        "image": [],
        "word": [],
        "excel": [],
        "text": [],
        "other": [],
    }

    for file_path in files:
        suffix = Path(file_path).suffix.lower()
        if suffix == ".pdf":
            groups["pdf"].append(file_path)
        elif suffix in {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}:
            groups["image"].append(file_path)
        elif suffix == ".docx":
            groups["word"].append(file_path)
        elif suffix in {".xlsx", ".xls"}:
            groups["excel"].append(file_path)
        elif suffix in {".txt", ".md"}:
            groups["text"].append(file_path)
        else:
            groups["other"].append(file_path)

    return ok(classified=groups)
