from __future__ import annotations

from typing import Any, Dict, List, Tuple

from agent.graphs.policy import get_policy_value
from agent.graphs.state import AppState


def _to_rows(source: Any) -> List[Dict[str, Any]]:
    if isinstance(source, list):
        return [item for item in source if isinstance(item, dict)]
    if isinstance(source, dict):
        for key in ("rows", "items", "records"):
            rows = source.get(key)
            if isinstance(rows, list):
                return [item for item in rows if isinstance(item, dict)]
        by_month = source.get("by_month")
        if isinstance(by_month, list):
            rows: List[Dict[str, Any]] = []
            for item in by_month:
                if not isinstance(item, dict):
                    continue
                rows.append({"month": item.get("month", "unknown"), "amount": item.get("amount", 0)})
            return rows
        if any(isinstance(value, (int, float)) for value in source.values()):
            total = source.get("total_amount", source.get("amount", 0))
            return [{"item": "TOTAL", "amount": total}]
    return []


def _row_amount(row: Dict[str, Any]) -> float:
    for key in ("amount", "budget_amount", "actual_amount", "total_amount", "value"):
        if key in row:
            try:
                return float(row.get(key, 0) or 0)
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def _row_key(row: Dict[str, Any], index: int) -> str:
    fields = []
    for key in ("period", "month", "department", "dept", "subject", "category", "project", "item", "name"):
        value = row.get(key)
        if value not in (None, ""):
            fields.append(str(value).strip())
    if fields:
        return "|".join(fields)
    return f"ROW_{index + 1}"


def _safe_float(raw: Any, default: float) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _thresholds(payload: Dict[str, Any]) -> Dict[str, float]:
    recon_policy = payload.get("recon_policy", {}) if isinstance(payload.get("recon_policy", {}), dict) else {}
    abs_threshold = _safe_float(recon_policy.get("abs_threshold", get_policy_value(payload, "recon_abs_threshold", 100)), 100.0)
    pct_threshold = _safe_float(
        recon_policy.get("pct_threshold", get_policy_value(payload, "recon_pct_threshold", 0.05)),
        0.05,
    )
    return {
        "abs_threshold": abs_threshold,
        "pct_threshold": pct_threshold,
        "abs_block_threshold": _safe_float(recon_policy.get("abs_block_threshold", abs_threshold * 5), abs_threshold * 5),
        "pct_block_threshold": _safe_float(recon_policy.get("pct_block_threshold", pct_threshold * 3), pct_threshold * 3),
    }


def _normalized_suggestion_rules(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    recon_policy = payload.get("recon_policy", {}) if isinstance(payload.get("recon_policy", {}), dict) else {}
    raw_rules = recon_policy.get("suggestion_rules", [])
    if not isinstance(raw_rules, list):
        return []
    rules: List[Dict[str, Any]] = []
    for item in raw_rules[:20]:
        if not isinstance(item, dict):
            continue
        suggestion = str(item.get("suggestion", "")).strip()
        if not suggestion:
            continue
        raw_tokens = item.get("reason_contains", [])
        if isinstance(raw_tokens, str):
            tokens = [raw_tokens.strip()] if raw_tokens.strip() else []
        elif isinstance(raw_tokens, list):
            tokens = [str(token).strip() for token in raw_tokens if str(token).strip()]
        else:
            tokens = []
        rules.append({"reason_contains": tokens, "suggestion": suggestion})
    return rules


def _suggestion_for_reason(reason: str, rules: List[Dict[str, Any]]) -> str:
    for rule in rules:
        tokens = rule.get("reason_contains", [])
        if not isinstance(tokens, list):
            continue
        if any(token and token in reason for token in tokens):
            return str(rule.get("suggestion", "")).strip()
    default_map = {
        "预算或决算中缺少对应项": "补齐预算类目与决算条目映射，并补充缺失凭证。",
        "超出阻断阈值": "建议调整预算类目或补充审批说明后再提交。",
        "超出预警阈值": "建议补充差异原因说明，并在决算备注中标注。",
        "存在轻微差异": "建议记录差异原因，保留支撑材料备查。",
    }
    return default_map.get(reason, "建议人工复核该差异项并补充依据。")


def _material_for_reason(reason: str) -> Tuple[str, str]:
    mapping = {
        "预算或决算中缺少对应项": ("预算调整审批单", "docs/recon/审批/预算调整审批单.pdf"),
        "超出阻断阈值": ("大额差异情况说明", "docs/recon/说明/大额差异说明.docx"),
        "超出预警阈值": ("差异说明附件", "docs/recon/说明/差异说明.docx"),
        "存在轻微差异": ("差异备注记录", "docs/recon/备注/差异备注.xlsx"),
    }
    return mapping.get(reason, ("人工复核记录", "docs/recon/复核/人工复核记录.docx"))


def route_after_recon_normalize(state: AppState) -> str:
    budget_rows = state.get("canonical_budget_rows", [])
    actual_rows = state.get("canonical_actual_rows", [])
    if state.get("errors") and not budget_rows and not actual_rows:
        return "ReconFailNode"
    if budget_rows or actual_rows:
        return "ReconCompareNode"
    return "ReconGenerateNode"


def recon_start_node(state: AppState) -> AppState:
    return {"task_progress": state.get("task_progress", []) + [{"step": "recon_start", "tool_name": "start"}]}


def recon_load_node(state: AppState) -> AppState:
    payload = state.get("payload", {})
    budget_source = payload.get("budget_source", payload.get("budget_data", payload.get("budget_rows", [])))
    actual_source = payload.get("actual_source", payload.get("final_data", payload.get("actual_rows", [])))
    return {
        "payload": {
            **payload,
            "_recon_budget_source": budget_source,
            "_recon_actual_source": actual_source,
        },
        "task_progress": state.get("task_progress", []) + [{"step": "recon_load", "tool_name": "load_recon_sources"}],
    }


def recon_normalize_node(state: AppState) -> AppState:
    payload = state.get("payload", {})
    budget_source = payload.get("_recon_budget_source", payload.get("budget_source", []))
    actual_source = payload.get("_recon_actual_source", payload.get("actual_source", []))
    budget_rows = _to_rows(budget_source)
    actual_rows = _to_rows(actual_source)
    canonical_budget_rows = [
        {"key": _row_key(row, index), "amount": _row_amount(row), "raw": row}
        for index, row in enumerate(budget_rows)
    ]
    canonical_actual_rows = [
        {"key": _row_key(row, index), "amount": _row_amount(row), "raw": row}
        for index, row in enumerate(actual_rows)
    ]
    return {
        "canonical_budget_rows": canonical_budget_rows,
        "canonical_actual_rows": canonical_actual_rows,
        "task_progress": state.get("task_progress", []) + [{"step": "recon_normalize", "tool_name": "normalize_rows"}],
    }


def recon_compare_node(state: AppState) -> AppState:
    payload = state.get("payload", {})
    thresholds = _thresholds(payload)
    budget_map = {str(item.get("key", "")): float(item.get("amount", 0.0) or 0.0) for item in state.get("canonical_budget_rows", [])}
    actual_map = {str(item.get("key", "")): float(item.get("amount", 0.0) or 0.0) for item in state.get("canonical_actual_rows", [])}
    keys = sorted(set(budget_map.keys()) | set(actual_map.keys()))
    differences: List[Dict[str, Any]] = []
    for key in keys:
        budget_value = float(budget_map.get(key, 0.0))
        actual_value = float(actual_map.get(key, 0.0))
        abs_diff = round(actual_value - budget_value, 2)
        pct_diff = round((abs_diff / budget_value) if budget_value else (1.0 if actual_value else 0.0), 6)
        item: Dict[str, Any] = {
            "key": key,
            "budget_amount": budget_value,
            "actual_amount": actual_value,
            "abs_diff": abs_diff,
            "pct_diff": pct_diff,
        }
        if key not in budget_map or key not in actual_map:
            item["severity"] = "blocking"
            item["reason"] = "预算或决算中缺少对应项"
        elif abs(abs_diff) > thresholds["abs_block_threshold"] or abs(pct_diff) > thresholds["pct_block_threshold"]:
            item["severity"] = "blocking"
            item["reason"] = "超出阻断阈值"
        elif abs(abs_diff) > thresholds["abs_threshold"] or abs(pct_diff) > thresholds["pct_threshold"]:
            item["severity"] = "warning"
            item["reason"] = "超出预警阈值"
        elif abs_diff != 0:
            item["severity"] = "hint"
            item["reason"] = "存在轻微差异"
        else:
            item["severity"] = "ok"
            item["reason"] = "一致"
        differences.append(item)
    return {
        "recon_differences": differences,
        "task_progress": state.get("task_progress", []) + [{"step": "recon_compare", "tool_name": "compare_budget_actual"}],
    }


def recon_compliance_node(state: AppState) -> AppState:
    findings: List[Dict[str, Any]] = []
    for item in state.get("recon_differences", []):
        severity = str(item.get("severity", "ok"))
        if severity == "ok":
            continue
        findings.append(
            {
                "problem_code": f"RECON_{severity.upper()}",
                "risk_level": "high" if severity == "blocking" else ("medium" if severity == "warning" else "low"),
                "evidence": {
                    "key": item.get("key"),
                    "budget_amount": item.get("budget_amount"),
                    "actual_amount": item.get("actual_amount"),
                    "abs_diff": item.get("abs_diff"),
                    "pct_diff": item.get("pct_diff"),
                },
                "reason": item.get("reason", ""),
                "severity": severity,
            }
        )
    return {
        "compliance_findings": findings,
        "task_progress": state.get("task_progress", []) + [{"step": "recon_compliance", "tool_name": "compliance_screen"}],
    }


def recon_suggest_node(state: AppState) -> AppState:
    rules = _normalized_suggestion_rules(state.get("payload", {}))
    suggestions: List[Dict[str, Any]] = []
    for finding in state.get("compliance_findings", []):
        reason = str(finding.get("reason", ""))
        suggestions.append(
            {
                "problem_code": finding.get("problem_code"),
                "risk_level": finding.get("risk_level"),
                "fix_action": _suggestion_for_reason(reason, rules),
                "required_materials": [],
            }
        )
    return {
        "fix_suggestions": suggestions,
        "task_progress": state.get("task_progress", []) + [{"step": "recon_suggest", "tool_name": "suggestion_engine"}],
    }


def recon_material_node(state: AppState) -> AppState:
    checklist: List[Dict[str, Any]] = []
    for finding in state.get("compliance_findings", []):
        reason = str(finding.get("reason", ""))
        material_name, suggested_path = _material_for_reason(reason)
        checklist.append(
            {
                "problem_code": finding.get("problem_code"),
                "material_name": material_name,
                "status": "missing",
                "suggested_path": suggested_path,
            }
        )
    return {
        "material_checklist": checklist,
        "task_progress": state.get("task_progress", []) + [{"step": "recon_material", "tool_name": "material_planner"}],
    }


def recon_generate_node(state: AppState) -> AppState:
    payload = state.get("payload", {})
    thresholds = _thresholds(payload)
    rules = _normalized_suggestion_rules(payload)
    differences = state.get("recon_differences", [])
    if not state.get("canonical_budget_rows") and not state.get("canonical_actual_rows"):
        result = {
            "type": "recon",
            "status": "needs_clarification",
            "message": "未提供可核对的数据，请补充 budget_source 与 actual_source（rows/items/by_month）。",
            "summary": {"total_items": 0, "blocking": 0, "warning": 0, "hint": 0},
            "differences": [],
            "thresholds": thresholds,
            "suggestion_rules": rules,
            "fix_suggestions": [],
            "material_checklist": [],
            "errors": state.get("errors", []),
        }
    else:
        blocking = [item for item in differences if str(item.get("severity")) == "blocking"]
        warning = [item for item in differences if str(item.get("severity")) == "warning"]
        hint = [item for item in differences if str(item.get("severity")) == "hint"]
        if blocking:
            status = "failed"
        elif warning:
            status = "warning"
        elif hint:
            status = "passed_with_hint"
        else:
            status = "passed"
        result = {
            "type": "recon",
            "status": status,
            "summary": {
                "total_items": len(differences),
                "blocking": len(blocking),
                "warning": len(warning),
                "hint": len(hint),
            },
            "thresholds": thresholds,
            "suggestion_rules": rules,
            "differences": differences,
            "blocking_items": blocking,
            "warning_items": warning,
            "hint_items": hint,
            "compliance_findings": state.get("compliance_findings", []),
            "fix_suggestions": state.get("fix_suggestions", []),
            "material_checklist": state.get("material_checklist", []),
            "errors": state.get("errors", []),
        }
    return {
        "result": result,
        "task_progress": state.get("task_progress", []) + [{"step": "recon_generate", "tool_name": "recon_result_builder"}],
    }


def recon_fail_node(state: AppState) -> AppState:
    errors = state.get("errors", [])
    return {
        "result": {
            "type": "recon",
            "status": "failed",
            "errors": errors,
        },
        "errors": errors,
        "task_progress": state.get("task_progress", []) + [{"step": "recon_fail", "tool_name": "fail_fast_guard"}],
    }
