from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from functools import lru_cache
from typing import Dict, Tuple


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
    enable_llm_checks: bool
    llm_model: str
    llm_temperature: float


@dataclass(frozen=True)
class GraphPolicyConfig:
    reimburse_stop_on_rule_violation: bool
    qa_allow_empty_query: bool
    qa_kb_top_k: int
    qa_kb_score_threshold: float
    final_generate_when_empty: bool
    budget_skip_calculate_when_empty: bool
    graph_enable_trace: bool


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


def _safe_bool(value: str, default: bool) -> bool:
    text = (value or "").strip().lower()
    if not text:
        return default
    return text in ("1", "true", "yes", "on")


def _safe_int(value: str, default: int, minimum: int = 1) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(parsed, minimum)


@lru_cache(maxsize=1)
def get_graph_policy_config() -> GraphPolicyConfig:
    return GraphPolicyConfig(
        reimburse_stop_on_rule_violation=_safe_bool(
            os.getenv("AGENT_GRAPH_REIMBURSE_STOP_ON_RULE_VIOLATION", "false"),
            False,
        ),
        qa_allow_empty_query=_safe_bool(
            os.getenv("AGENT_GRAPH_QA_ALLOW_EMPTY_QUERY", "false"),
            False,
        ),
        qa_kb_top_k=_safe_int(
            os.getenv("AGENT_GRAPH_QA_KB_TOP_K", "4"),
            4,
            minimum=1,
        ),
        qa_kb_score_threshold=_safe_float(
            os.getenv("AGENT_GRAPH_QA_KB_SCORE_THRESHOLD", "0.55"),
            0.55,
        ),
        final_generate_when_empty=_safe_bool(
            os.getenv("AGENT_GRAPH_FINAL_GENERATE_WHEN_EMPTY", "true"),
            True,
        ),
        budget_skip_calculate_when_empty=_safe_bool(
            os.getenv("AGENT_GRAPH_BUDGET_SKIP_CALCULATE_WHEN_EMPTY", "true"),
            True,
        ),
        graph_enable_trace=_safe_bool(
            os.getenv("AGENT_GRAPH_ENABLE_TRACE", "false"),
            False,
        ),
    )


def get_graph_policy_defaults() -> Dict[str, object]:
    return asdict(get_graph_policy_config())
