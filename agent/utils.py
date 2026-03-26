from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from .schemas import CATEGORY_SYNONYMS

try:
    from jsonschema import ValidationError, validate
except Exception:  # pragma: no cover
    ValidationError = ValueError
    validate = None


def safe_load_payload(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError(f"输入不是合法 JSON: {exc}") from exc
    raise TypeError("仅支持 dict 或 JSON 字符串作为输入")


def validate_payload_schema(payload: Dict[str, Any], schema: Dict[str, Any], label: str) -> None:
    if validate is not None:
        try:
            validate(instance=payload, schema=schema)
        except ValidationError as exc:
            path = ".".join(str(item) for item in getattr(exc, "absolute_path", [])) or "<root>"
            raise ValueError(f"{label} 字段校验失败: {path} - {exc.message}") from exc
        return
    if not isinstance(payload, dict):
        raise ValueError(f"{label} 必须是对象")
    if "items" not in payload or not isinstance(payload["items"], list):
        raise ValueError(f"{label} 缺少 items 数组")


def normalize_text(value: Optional[str]) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def append_discrepancy(
    state_items: List[Dict[str, Any]],
    *,
    issue_type: str,
    risk: str,
    message: str,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    payload = {"type": issue_type, "risk": risk, "message": message}
    if details:
        payload["details"] = details
        payload.update(details)
    state_items.append(payload)


def dedupe_keep_order(items: List[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def build_budget_alias_map(budget_df: pd.DataFrame) -> Dict[str, str]:
    alias_map: Dict[str, str] = {}
    for _, row in budget_df.iterrows():
        category = row["category"]
        alias_map[normalize_text(category)] = category

        aliases = row.get("aliases", [])
        if isinstance(aliases, list):
            for alias in aliases:
                alias_map[normalize_text(str(alias))] = category

    for alias, category in CATEGORY_SYNONYMS.items():
        alias_map[normalize_text(alias)] = category

    return alias_map


def fuzzy_align_category(
    expense_type: str,
    claimed_category: str,
    budget_categories: List[str],
    alias_map: Dict[str, str],
) -> Tuple[Optional[str], str]:
    from difflib import get_close_matches

    claimed_norm = normalize_text(claimed_category)
    expense_norm = normalize_text(expense_type)

    if claimed_norm in alias_map:
        return alias_map[claimed_norm], "exact_claimed"
    if expense_norm in alias_map:
        return alias_map[expense_norm], "exact_expense"

    for key, mapped_category in alias_map.items():
        if key and key in claimed_norm:
            return mapped_category, "contain_claimed"
    for key, mapped_category in alias_map.items():
        if key and key in expense_norm:
            return mapped_category, "contain_expense"

    budget_norm_to_raw = {normalize_text(category): category for category in budget_categories}
    budget_norm_keys = list(budget_norm_to_raw.keys())

    claim_hits = get_close_matches(claimed_norm, budget_norm_keys, n=1, cutoff=0.55)
    if claim_hits:
        return budget_norm_to_raw[claim_hits[0]], "fuzzy_claimed"

    expense_hits = get_close_matches(expense_norm, budget_norm_keys, n=1, cutoff=0.55)
    if expense_hits:
        return budget_norm_to_raw[expense_hits[0]], "fuzzy_expense"

    return None, "unmatched"
