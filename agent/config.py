from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Tuple


def _safe_float(value: str, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_csv(value: str, default: Tuple[str, ...]) -> Tuple[str, ...]:
    items = tuple(part.strip() for part in (value or "").split(",") if part.strip())
    return items or default


@dataclass(frozen=True)
class AuditConfig:
    category_overrun_threshold: float
    high_risk_label: str
    special_expense_keywords: Tuple[str, ...]


@lru_cache(maxsize=1)
def get_audit_config() -> AuditConfig:
    threshold = _safe_float(os.getenv("AGENT_CATEGORY_OVERRUN_THRESHOLD", "0.10"), 0.10)
    high_risk_label = os.getenv("AGENT_HIGH_RISK_LABEL", "High Risk").strip() or "High Risk"
    special_keywords = _safe_csv(
        os.getenv("AGENT_SPECIAL_EXPENSE_KEYWORDS", "餐饮,会议"),
        ("餐饮", "会议"),
    )
    return AuditConfig(
        category_overrun_threshold=max(threshold, 0.0),
        high_risk_label=high_risk_label,
        special_expense_keywords=special_keywords,
    )
