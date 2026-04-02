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


def _safe_bool(value: str, default: bool) -> bool:
    raw = (value or "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "y", "on"}:
        return True
    if raw in {"0", "false", "no", "n", "off"}:
        return False
    return default


@dataclass(frozen=True)
class AuditConfig:
    category_overrun_threshold: float
    high_risk_label: str
    special_expense_keywords: Tuple[str, ...]
    enable_llm_checks: bool
    llm_model: str
    llm_temperature: float


@dataclass(frozen=True)
class RAGTraceConfig:
    enabled: bool
    trace_dir: str


@lru_cache(maxsize=1)
def get_audit_config() -> AuditConfig:
    threshold = _safe_float(os.getenv("AGENT_CATEGORY_OVERRUN_THRESHOLD", "0.10"), 0.10)
    high_risk_label = os.getenv("AGENT_HIGH_RISK_LABEL", "High Risk").strip() or "High Risk"
    special_keywords = _safe_csv(
        os.getenv("AGENT_SPECIAL_EXPENSE_KEYWORDS", "餐饮,会议"),
        ("餐饮", "会议"),
    )
    # Only enable LLM-based audit checks when explicitly configured

    enable_llm = os.getenv("AGENT_ENABLE_LLM_CHECKS", "").strip().lower() in ("1", "true", "yes")
    llm_model = os.getenv("AGENT_LLM_MODEL", "DeepSeekV3.2")
    llm_temp = _safe_float(os.getenv("AGENT_LLM_TEMPERATURE", "0.0"), 0.0)
    return AuditConfig(
        category_overrun_threshold=max(threshold, 0.0),
        high_risk_label=high_risk_label,
        special_expense_keywords=special_keywords,
        enable_llm_checks=enable_llm,
        llm_model=llm_model,
        llm_temperature=llm_temp,
    )


@lru_cache(maxsize=1)
def get_rag_trace_config() -> RAGTraceConfig:
    enabled = _safe_bool(os.getenv("AGENT_RAG_TRACE_ENABLED", "1"), True)
    trace_dir = os.getenv("AGENT_RAG_TRACE_DIR", "").strip() or "data/eval/traces"
    return RAGTraceConfig(enabled=enabled, trace_dir=trace_dir)
