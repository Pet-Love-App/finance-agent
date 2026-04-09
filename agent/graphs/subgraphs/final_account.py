from __future__ import annotations

from typing import Any, Dict, List

from agent.graphs.policy import get_bool_policy, get_policy_value
from agent.graphs.state import AppState
from agent.tools import aggregate_records, data_clean, generate_final_account, load_records


def final_start_node(state: AppState) -> AppState:
    return {"task_progress": state.get("task_progress", []) + [{"step": "final_start", "tool_name": "start"}]}


def route_after_load_records(state: AppState) -> str:
    payload = state.get("payload", {})
    records = state.get("records", [])
    if state.get("errors") and not records:
        return "FinalFailNode"
    generate_when_empty = get_bool_policy(payload, "final_generate_when_empty", True)
    if records:
        return "DataCleanNode"
    return "FinalGenerateNode" if generate_when_empty else "DataCleanNode"


def route_after_data_clean(state: AppState) -> str:
    payload = state.get("payload", {})
    records = state.get("records", [])
    if state.get("errors") and not records:
        return "FinalFailNode"
    generate_when_empty = get_bool_policy(payload, "final_generate_when_empty", True)
    if records:
        return "DataAggregateNode"
    return "FinalGenerateNode" if generate_when_empty else "DataAggregateNode"


def load_records_node(state: AppState) -> AppState:
    res = load_records(state.get("payload", {}).get("filters", {}), state.get("payload", {}).get("db_path"))
    return {
        "records": res.data.get("records", []),
        "errors": state.get("errors", []) + ([res.error] if res.error else []),
        "task_progress": state.get("task_progress", []) + [{"step": "load_records", "tool_name": "load_records"}],
    }


def data_clean_node(state: AppState) -> AppState:
    res = data_clean(state.get("records", []))
    return {
        "records": res.data.get("cleaned", []),
        "errors": state.get("errors", []) + ([res.error] if res.error else []),
        "task_progress": state.get("task_progress", []) + [{"step": "data_clean", "tool_name": "data_clean"}],
    }


def aggregate_node(state: AppState) -> AppState:
    res = aggregate_records(state.get("records", []))
    return {
        "aggregate": res.data.get("aggregate", {}),
        "errors": state.get("errors", []) + ([res.error] if res.error else []),
        "task_progress": state.get("task_progress", []) + [{"step": "aggregate", "tool_name": "aggregate_records"}],
    }


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


def _build_recon_result(state: AppState) -> Dict[str, Any]:
    payload = state.get("payload", {})
    recon_policy = payload.get("recon_policy", {}) if isinstance(payload.get("recon_policy", {}), dict) else {}
    raw_suggestion_rules = recon_policy.get("suggestion_rules", [])
    suggestion_rules: List[Dict[str, Any]] = []
    if isinstance(raw_suggestion_rules, list):
        for item in raw_suggestion_rules[:20]:
            if not isinstance(item, dict):
                continue
            reason_contains = item.get("reason_contains", [])
            suggestion = str(item.get("suggestion", "")).strip()
            if not suggestion:
                continue
            if isinstance(reason_contains, str):
                normalized_tokens = [reason_contains.strip()] if reason_contains.strip() else []
            elif isinstance(reason_contains, list):
                normalized_tokens = [str(token).strip() for token in reason_contains if str(token).strip()]
            else:
                normalized_tokens = []
            suggestion_rules.append({"reason_contains": normalized_tokens, "suggestion": suggestion})
    abs_threshold = _safe_float(recon_policy.get("abs_threshold", get_policy_value(payload, "recon_abs_threshold", 100)), 100.0)
    pct_threshold = _safe_float(
        recon_policy.get("pct_threshold", get_policy_value(payload, "recon_pct_threshold", 0.05)),
        0.05,
    )
    abs_block_threshold = _safe_float(
        recon_policy.get("abs_block_threshold", abs_threshold * 5),
        abs_threshold * 5,
    )
    pct_block_threshold = _safe_float(
        recon_policy.get("pct_block_threshold", pct_threshold * 3),
        pct_threshold * 3,
    )

    budget_rows = _to_rows(payload.get("budget_source", payload.get("budget_data", payload.get("budget_rows", []))))
    actual_rows = _to_rows(payload.get("actual_source", payload.get("final_data", payload.get("actual_rows", []))))

    if not budget_rows and not actual_rows:
        return {
            "type": "recon",
            "status": "needs_clarification",
            "message": "未提供可核对的数据，请补充 budget_source 与 actual_source（rows/items/by_month）。",
            "summary": {"total_items": 0, "blocking": 0, "warning": 0, "hint": 0},
            "differences": [],
            "thresholds": {
                "abs_threshold": abs_threshold,
                "pct_threshold": pct_threshold,
                "abs_block_threshold": abs_block_threshold,
                "pct_block_threshold": pct_block_threshold,
            },
            "suggestion_rules": suggestion_rules,
            "errors": state.get("errors", []),
        }

    budget_map: Dict[str, float] = {}
    actual_map: Dict[str, float] = {}
    for index, row in enumerate(budget_rows):
        budget_map[_row_key(row, index)] = _row_amount(row)
    for index, row in enumerate(actual_rows):
        actual_map[_row_key(row, index)] = _row_amount(row)

    keys = sorted(set(budget_map.keys()) | set(actual_map.keys()))
    blocking: List[Dict[str, Any]] = []
    warning: List[Dict[str, Any]] = []
    hint: List[Dict[str, Any]] = []
    differences: List[Dict[str, Any]] = []

    for key in keys:
        budget_value = float(budget_map.get(key, 0.0))
        actual_value = float(actual_map.get(key, 0.0))
        abs_diff = round(actual_value - budget_value, 2)
        pct_diff = round((abs_diff / budget_value) if budget_value else (1.0 if actual_value else 0.0), 6)
        item = {
            "key": key,
            "budget_amount": budget_value,
            "actual_amount": actual_value,
            "abs_diff": abs_diff,
            "pct_diff": pct_diff,
        }
        if key not in budget_map or key not in actual_map:
            item["severity"] = "blocking"
            item["reason"] = "预算或决算中缺少对应项"
            blocking.append(item)
        elif abs(abs_diff) > abs_block_threshold or abs(pct_diff) > pct_block_threshold:
            item["severity"] = "blocking"
            item["reason"] = "超出阻断阈值"
            blocking.append(item)
        elif abs(abs_diff) > abs_threshold or abs(pct_diff) > pct_threshold:
            item["severity"] = "warning"
            item["reason"] = "超出预警阈值"
            warning.append(item)
        elif abs_diff != 0:
            item["severity"] = "hint"
            item["reason"] = "存在轻微差异"
            hint.append(item)
        else:
            item["severity"] = "ok"
            item["reason"] = "一致"
        differences.append(item)

    status = "passed"
    if blocking:
        status = "failed"
    elif warning:
        status = "warning"
    elif hint:
        status = "passed_with_hint"

    return {
        "type": "recon",
        "status": status,
        "summary": {
            "total_items": len(keys),
            "blocking": len(blocking),
            "warning": len(warning),
            "hint": len(hint),
        },
        "thresholds": {
            "abs_threshold": abs_threshold,
            "pct_threshold": pct_threshold,
            "abs_block_threshold": abs_block_threshold,
            "pct_block_threshold": pct_block_threshold,
        },
        "suggestion_rules": suggestion_rules,
        "differences": differences,
        "blocking_items": blocking,
        "warning_items": warning,
        "hint_items": hint,
        "errors": state.get("errors", []),
    }


def final_generate_node(state: AppState) -> AppState:
    route_decision = state.get("route_decision", {}) if isinstance(state.get("route_decision", {}), dict) else {}
    route_task_type = str(route_decision.get("task_type", "")).strip().lower()
    if route_task_type == "recon":
        recon_result = _build_recon_result(state)
        return {
            "result": recon_result,
            "task_progress": state.get("task_progress", []) + [{"step": "recon_generate", "tool_name": "reconciliation_engine"}],
        }

    aggregate = state.get("aggregate", {"total_amount": 0.0, "count": 0, "by_month": []})
    res = generate_final_account(aggregate, state.get("payload", {}).get("output_dir"))
    errors = state.get("errors", []) + ([res.error] if res.error else [])
    return {
        "outputs": {**state.get("outputs", {}), "final_account_path": res.data.get("final_account_path", "")},
        "result": {
            "type": "final_account",
            "aggregate": aggregate,
            "final_account_path": res.data.get("final_account_path", ""),
            "errors": errors,
        },
        "errors": errors,
        "task_progress": state.get("task_progress", []) + [{"step": "final_generate", "tool_name": "generate_final_account"}],
    }


def final_fail_node(state: AppState) -> AppState:
    errors = state.get("errors", [])
    return {
        "result": {
            "type": "final_account",
            "status": "failed",
            "errors": errors,
        },
        "errors": errors,
        "task_progress": state.get("task_progress", []) + [{"step": "final_fail", "tool_name": "fail_fast_guard"}],
    }
