from __future__ import annotations

from typing import Any, Dict, List, Tuple

from agent.graphs.state import AppState


TASK_QA = "qa"
TASK_REIMBURSE = "reimburse"
TASK_FINAL = "final_account"
TASK_BUDGET = "budget"
TASK_SANDBOX = "sandbox_exec"
TASK_FILE_EDIT = "file_edit"

TASK_RECON = "recon"
TASK_MATERIAL = "material"
TASK_BUDGET_FILL = "budget_fill"
TASK_FINAL_FILL = "final_fill"


def _append_reason(reasons: List[str], code: str) -> None:
    if code not in reasons:
        reasons.append(code)


def _to_bool(raw: Any) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    return bool(raw)


def _normalize_explicit_task(task_type: str) -> str:
    text = str(task_type or "").strip().lower()
    if text in {"", "auto"}:
        return ""
    alias_map = {
        "t1_qa": TASK_QA,
        "t2_recon": TASK_RECON,
        "t3_material": TASK_MATERIAL,
        "t4_budget_fill": TASK_BUDGET_FILL,
        "t5_final_fill": TASK_FINAL_FILL,
        "t6_file_edit": TASK_FILE_EDIT,
        "qa": TASK_QA,
        "reimburse": TASK_REIMBURSE,
        "final_account": TASK_FINAL,
        "budget": TASK_BUDGET,
        "sandbox_exec": TASK_SANDBOX,
        "file_edit": TASK_FILE_EDIT,
        "recon": TASK_RECON,
        "material": TASK_MATERIAL,
        "budget_fill": TASK_BUDGET_FILL,
        "final_fill": TASK_FINAL_FILL,
    }
    return alias_map.get(text, "")


def _classify_task(query: str, payload: Dict[str, Any]) -> Tuple[str, float, List[str]]:
    text = str(query or "").strip().lower()
    reasons: List[str] = []
    if not text:
        _append_reason(reasons, "R800_EMPTY_QUERY")
        return TASK_REIMBURSE, 0.52, reasons

    if any(key in text for key in ("xlsx_edit", "replace_text", "write_file", "append_file")):
        _append_reason(reasons, "R601_TOOL_ACTION")
        return TASK_FILE_EDIT, 0.95, reasons

    if any(
        key in text
        for key in (
            "修改文件",
            "编辑文件",
            "替换文本",
            "批量改表",
            "写入文件",
            "当前文件",
            "这个文件",
            "新增",
            "加入",
            "追加",
            "测试数据",
        )
    ):
        _append_reason(reasons, "R602_FILE_EDIT")
        return TASK_FILE_EDIT, 0.91, reasons

    has_budget = any(key in text for key in ("预算", "budget"))
    has_final = any(key in text for key in ("决算", "final", "结项"))
    has_check = any(key in text for key in ("核对", "比对", "差异", "勾稽", "一致性"))
    has_fill = any(key in text for key in ("填写", "回填", "填报"))

    if has_budget and has_final and has_check:
        _append_reason(reasons, "R201_RECON")
        return TASK_RECON, 0.9, reasons

    if has_budget and has_fill:
        _append_reason(reasons, "R401_BUDGET_FILL")
        return TASK_BUDGET_FILL, 0.88, reasons

    if has_final and has_fill:
        _append_reason(reasons, "R501_FINAL_FILL")
        return TASK_FINAL_FILL, 0.88, reasons

    if any(key in text for key in ("整理材料", "报销材料", "附件整理", "打包", "归档")):
        _append_reason(reasons, "R301_MATERIAL")
        return TASK_MATERIAL, 0.86, reasons

    if any(key in text for key in ("报销规则", "能不能报", "附件要求", "制度", "口径")):
        _append_reason(reasons, "R101_QA")
        return TASK_QA, 0.85, reasons

    if has_budget:
        _append_reason(reasons, "R402_BUDGET")
        return TASK_BUDGET, 0.74, reasons

    if has_final:
        _append_reason(reasons, "R502_FINAL")
        return TASK_FINAL, 0.74, reasons

    if any(key in text for key in ("报销", "发票", "附件")):
        _append_reason(reasons, "R302_REIMBURSE")
        return TASK_REIMBURSE, 0.72, reasons

    referenced_files = payload.get("referenced_files", [])
    if isinstance(referenced_files, list) and any(str(item).strip() for item in referenced_files):
        _append_reason(reasons, "R604_REFERENCED_FILES")
        return TASK_FILE_EDIT, 0.86, reasons

    if _to_bool(payload.get("workspace_mode", False)):
        _append_reason(reasons, "R603_WORKSPACE_HINT")
        return TASK_FILE_EDIT, 0.68, reasons

    _append_reason(reasons, "R899_FALLBACK")
    return TASK_REIMBURSE, 0.56, reasons


def _to_runtime_task(task_type: str) -> str:
    mapping = {
        TASK_QA: TASK_QA,
        TASK_REIMBURSE: TASK_REIMBURSE,
        TASK_FINAL: TASK_FINAL,
        TASK_BUDGET: TASK_BUDGET,
        TASK_SANDBOX: TASK_SANDBOX,
        TASK_FILE_EDIT: TASK_FILE_EDIT,
        TASK_RECON: TASK_FINAL,
        TASK_MATERIAL: TASK_REIMBURSE,
        TASK_BUDGET_FILL: TASK_BUDGET,
        TASK_FINAL_FILL: TASK_FINAL,
    }
    return mapping.get(task_type, TASK_REIMBURSE)


def _with_confirmation_policy(payload: Dict[str, Any], *, requires_confirmation: bool) -> Dict[str, Any]:
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        policy = {}
    if requires_confirmation:
        policy = {**policy, "requires_confirmation": True}
    else:
        policy = {**policy, "requires_confirmation": bool(policy.get("requires_confirmation", False))}
    if "confirmed" not in policy:
        policy["confirmed"] = False
    return {**payload, "policy": policy}


def _is_confirmed(payload: Dict[str, Any]) -> bool:
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        return False
    return _to_bool(policy.get("confirmed", False))


def intent_node(state: AppState) -> AppState:
    payload: Dict[str, Any] = state.get("payload", {})
    explicit_task = _normalize_explicit_task(str(state.get("task_type", "")).strip().lower())
    if explicit_task:
        runtime_task = _to_runtime_task(explicit_task)
        risk_level = "high" if explicit_task in {TASK_FILE_EDIT, TASK_BUDGET_FILL, TASK_FINAL_FILL} else "medium"
        requires_confirmation = explicit_task in {TASK_FILE_EDIT, TASK_BUDGET_FILL, TASK_FINAL_FILL}
        next_payload = _with_confirmation_policy(payload, requires_confirmation=requires_confirmation)
        return {
            "task_type": runtime_task,
            "route_decision": {
                "task_type": explicit_task,
                "runtime_task_type": runtime_task,
                "confidence": 1.0,
                "risk_level": risk_level,
                "requires_confirmation": requires_confirmation,
                "reason_codes": ["R000_EXPLICIT_TASK"],
            },
            "payload": next_payload,
            "task_progress": state.get("task_progress", [])
            + [{"step": "intent", "tool_name": "supervisor_route", "task_type": runtime_task}],
        }

    query = str(payload.get("query", ""))
    inferred_task, confidence, reason_codes = _classify_task(query, payload)
    runtime_task = _to_runtime_task(inferred_task)
    is_write_task = inferred_task in {TASK_FILE_EDIT, TASK_BUDGET_FILL, TASK_FINAL_FILL, TASK_MATERIAL}
    risk_level = "high" if is_write_task else "medium"
    requires_confirmation = is_write_task and confidence >= 0.8
    next_payload = _with_confirmation_policy(payload, requires_confirmation=requires_confirmation)

    return {
        "task_type": runtime_task,
        "route_decision": {
            "task_type": inferred_task,
            "runtime_task_type": runtime_task,
            "confidence": round(float(confidence), 3),
            "risk_level": risk_level,
            "requires_confirmation": requires_confirmation,
            "reason_codes": reason_codes,
            "clarification_required": confidence < 0.8,
        },
        "payload": {
            **next_payload,
            "route_decision": {
                "task_type": inferred_task,
                "confidence": round(float(confidence), 3),
                "reason_codes": reason_codes,
            },
        },
        "task_progress": state.get("task_progress", [])
        + [{"step": "intent", "tool_name": "supervisor_route", "task_type": runtime_task}],
    }


def intent_clarify_node(state: AppState) -> AppState:
    payload = state.get("payload", {})
    query = str(payload.get("query", "")).strip()
    route_decision = state.get("route_decision", {}) if isinstance(state.get("route_decision", {}), dict) else {}
    inferred_task = str(route_decision.get("task_type", "")).strip() or "unknown"
    confidence = float(route_decision.get("confidence", 0.0) or 0.0)
    reason_codes = route_decision.get("reason_codes", [])
    message = (
        "当前请求意图不够明确，请补充目标任务（如：报销审核/制度问答/决算生成/预算生成/文件修改）"
        "以及输入数据范围后再执行。"
    )
    return {
        "result": {
            "type": "clarification",
            "status": "needs_clarification",
            "message": message,
            "query": query,
            "inferred_task": inferred_task,
            "confidence": round(confidence, 3),
            "reason_codes": reason_codes if isinstance(reason_codes, list) else [],
            "errors": state.get("errors", []),
        },
        "task_progress": state.get("task_progress", [])
        + [{"step": "intent_clarify", "tool_name": "clarification_guard"}],
    }


def intent_confirm_node(state: AppState) -> AppState:
    payload = state.get("payload", {})
    route_decision = state.get("route_decision", {}) if isinstance(state.get("route_decision", {}), dict) else {}
    runtime_task = str(route_decision.get("runtime_task_type", state.get("task_type", TASK_REIMBURSE)))
    inferred_task = str(route_decision.get("task_type", runtime_task))
    confirmed = _is_confirmed(payload)
    if confirmed:
        return {
            "task_progress": state.get("task_progress", [])
            + [{"step": "intent_confirmed", "tool_name": "confirmation_guard"}]
        }
    return {
        "result": {
            "type": "confirmation",
            "status": "pending_confirmation",
            "task_type": inferred_task,
            "runtime_task_type": runtime_task,
            "message": "检测到高风险写操作，请先确认 policy.confirmed=true 后再执行。",
            "errors": state.get("errors", []),
        },
        "task_progress": state.get("task_progress", [])
        + [{"step": "intent_confirm", "tool_name": "confirmation_guard"}],
    }


def route_by_task(state: AppState) -> str:
    route_decision = state.get("route_decision", {}) if isinstance(state.get("route_decision", {}), dict) else {}
    payload = state.get("payload", {}) if isinstance(state.get("payload", {}), dict) else {}
    if _to_bool(route_decision.get("clarification_required", False)):
        return "IntentClarifyNode"
    if _to_bool(route_decision.get("requires_confirmation", False)) and not _is_confirmed(payload):
        return "IntentConfirmNode"

    task_type = str(state.get("task_type", TASK_REIMBURSE))
    if task_type == TASK_QA:
        return "QAStartNode"
    if task_type == TASK_FINAL:
        return "FinalStartNode"
    if task_type == TASK_BUDGET:
        return "BudgetStartNode"
    if task_type == TASK_SANDBOX:
        return "SandboxStartNode"
    if task_type == TASK_FILE_EDIT:
        return "FileEditStartNode"
    return "ReimburseStartNode"
