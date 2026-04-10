from __future__ import annotations

import datetime
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

DEFAULT_REIMBURSE_CATEGORY_KEYWORDS: Dict[str, Set[str]] = {
    "报销单": {"报销单", "报销申请", "报销", "reimburse"},
    "发票": {"发票", "invoice", "票据", "电子票"},
    "支付凭证": {"支付", "付款", "转账", "流水", "回单", "payment"},
    "费用明细": {"明细", "清单", "detail"},
    "活动说明": {"活动说明", "情况说明", "说明", "通知", "邮件", "mail"},
    "预算材料": {"预算", "budget"},
    "决算材料": {"决算", "final", "结项"},
    "签到材料": {"签到", "签名", "出席"},
}

DEFAULT_REQUIRED_CATEGORIES = ["报销单", "发票", "支付凭证", "费用明细"]

DEFAULT_MISSING_SUGGESTIONS: Dict[str, str] = {
    "报销单": "示例：报销单.xlsx / 报销申请表.docx",
    "发票": "示例：发票1.pdf / 电子发票.png",
    "支付凭证": "示例：支付回单.pdf / 转账截图.jpg",
    "费用明细": "示例：费用明细.xlsx / 报销清单.csv",
}


def _match_keywords(text: str, keywords: Set[str]) -> bool:
    lowered = text.lower()
    return any(key.lower() in lowered for key in keywords)


def _parse_reimburse_package_options(raw_options: Any) -> Tuple[Dict[str, Set[str]], List[str], Dict[str, str], bool]:
    category_keywords: Dict[str, Set[str]] = {
        key: set(values) for key, values in DEFAULT_REIMBURSE_CATEGORY_KEYWORDS.items()
    }
    required_categories = list(DEFAULT_REQUIRED_CATEGORIES)
    suggestions = dict(DEFAULT_MISSING_SUGGESTIONS)
    include_uncategorized = True

    if not isinstance(raw_options, dict):
        return category_keywords, required_categories, suggestions, include_uncategorized

    custom_keywords = raw_options.get("category_keywords")
    if isinstance(custom_keywords, dict):
        for category, values in custom_keywords.items():
            key = str(category).strip()
            if not key:
                continue
            if isinstance(values, list):
                words = {str(item).strip() for item in values if str(item).strip()}
                if words:
                    category_keywords[key] = words

    custom_required = raw_options.get("required_categories")
    if isinstance(custom_required, list):
        normalized_required = [str(item).strip() for item in custom_required if str(item).strip()]
        if normalized_required:
            required_categories = normalized_required
            for category in required_categories:
                category_keywords.setdefault(category, {category})

    custom_suggestions = raw_options.get("missing_suggestions")
    if isinstance(custom_suggestions, dict):
        for category, tip in custom_suggestions.items():
            key = str(category).strip()
            if not key:
                continue
            tip_text = str(tip).strip()
            if tip_text:
                suggestions[key] = tip_text

    include_uncategorized = bool(raw_options.get("include_uncategorized", True))
    return category_keywords, required_categories, suggestions, include_uncategorized


def _all_workspace_files(root: Path, *, max_files: int = 5000) -> List[Path]:
    files: List[Path] = []
    for item in root.rglob("*"):
        if not item.is_file():
            continue
        try:
            item.relative_to(root)
        except ValueError:
            continue
        if item.suffix.lower() == ".zip":
            continue
        files.append(item)
        if len(files) >= max_files:
            break
    return files


def prepare_reimbursement_package(
    root: Path,
    package_name: str | None = None,
    options: Dict[str, Any] | None = None,
) -> str:
    all_files = _all_workspace_files(root)
    if not all_files:
        raise ValueError("目录为空，未找到可打包的材料。")

    category_keywords, required_categories, suggestion_map, include_uncategorized = _parse_reimburse_package_options(
        options or {}
    )

    category_files: Dict[str, List[Path]] = {key: [] for key in category_keywords.keys()}
    uncategorized: List[Path] = []

    for file_path in all_files:
        filename = file_path.name
        rel = str(file_path.relative_to(root)).replace("\\", "/")
        matched = False
        for category, keywords in category_keywords.items():
            if _match_keywords(filename, keywords) or _match_keywords(rel, keywords):
                category_files[category].append(file_path)
                matched = True
        if not matched:
            uncategorized.append(file_path)

    missing = [name for name in required_categories if not category_files.get(name)]
    if missing:
        details = "\n".join(f"- 缺少：{name}（{suggestion_map.get(name, '请补充对应材料')}）" for name in missing)
        raise ValueError(f"检测到材料不完整，请先补齐后再打包：\n{details}")

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_name = str(package_name or f"reimbursement_package_{timestamp}.zip").strip()
    if not raw_name.lower().endswith(".zip"):
        raw_name += ".zip"

    output_zip = (root / raw_name).resolve()
    try:
        output_zip.relative_to(root)
    except ValueError as exc:
        raise ValueError("压缩包名称非法，请仅提供文件名，不要包含目录穿越路径。") from exc

    with zipfile.ZipFile(output_zip, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for category, files in category_files.items():
            for file_path in files:
                zf.write(file_path, arcname=f"{category}/{file_path.name}")
        if include_uncategorized:
            for file_path in uncategorized:
                zf.write(file_path, arcname=f"其他材料/{file_path.name}")

    total_count = sum(len(files) for files in category_files.values()) + (len(uncategorized) if include_uncategorized else 0)
    summary_items = [f"{name} {len(category_files.get(name, []))} 份" for name in required_categories]
    return (
        f"已生成压缩包：{output_zip.name}（共 {total_count} 个文件）\n"
        f"分类统计：{', '.join(summary_items)}"
    )
