from __future__ import annotations

from typing import Dict, List

from agent.graphs.policy import get_bool_policy
from agent.graphs.state import AppState
from agent.tools import (
    check_rules,
    classify_files,
    extract_invoice_fields,
    extract_text_from_files,
    generate_email_draft,
    generate_excel_sheet,
    generate_word_doc,
    parse_activity,
    save_record,
    scan_inputs,
    send_or_export_email,
)


def _append_error(state: AppState, message: str) -> Dict[str, List[str]]:
    return {"errors": state.get("errors", []) + [message]}


def route_after_scan(state: AppState) -> str:
    if state.get("errors"):
        return "ReimburseFailNode"
    files = state.get("files", [])
    return "ClassifyFileNode" if files else "SaveRecordNode"


def route_after_extract(state: AppState) -> str:
    if state.get("errors"):
        return "ReimburseFailNode"
    merged_text = str(state.get("merged_text", "")).strip()
    return "InvoiceExtractNode" if merged_text else "ActivityParseNode"


def route_after_rule_check(state: AppState) -> str:
    payload = state.get("payload", {})
    stop_on_violation = get_bool_policy(
        payload,
        "reimburse_stop_on_rule_violation",
        False,
        legacy_keys=("stop_on_rule_violation",),
    )
    rule_result = state.get("rule_result", {})
    compliance = bool(rule_result.get("compliance", False))
    if stop_on_violation and not compliance:
        return "SaveRecordNode"
    return "GenDocNode"


def reimburse_start_node(state: AppState) -> AppState:
    return {"task_progress": state.get("task_progress", []) + [{"step": "reimburse_start", "tool_name": "start"}]}


def scan_file_node(state: AppState) -> AppState:
    payload = state.get("payload", {})
    paths: List[str] = list(payload.get("paths", []))
    res = scan_inputs(paths)
    if not res.success:
        return {
            "errors": state.get("errors", []) + [res.error or "scan_inputs 失败"],
            "task_progress": state.get("task_progress", []) + [{"step": "scan", "tool_name": "scan_inputs"}],
        }
    return {
        "files": res.data.get("files", []),
        "task_progress": state.get("task_progress", []) + [{"step": "scan", "tool_name": "scan_inputs"}],
    }


def classify_file_node(state: AppState) -> AppState:
    res = classify_files(state.get("files", []))
    if not res.success:
        return {
            **_append_error(state, res.error or "classify_files 失败"),
            "task_progress": state.get("task_progress", []) + [{"step": "classify", "tool_name": "classify_files"}],
        }
    return {
        "classified_files": res.data.get("classified", {}),
        "task_progress": state.get("task_progress", []) + [{"step": "classify", "tool_name": "classify_files"}],
    }


def extract_node(state: AppState) -> AppState:
    res = extract_text_from_files(state.get("classified_files", {}))
    if not res.success:
        return {
            **_append_error(state, res.error or "extract_text_from_files 失败"),
            "task_progress": state.get("task_progress", []) + [{"step": "extract", "tool_name": "extract_text_from_files"}],
        }
    return {
        "merged_text": res.data.get("merged_text", ""),
        "file_text_map": res.data.get("file_text_map", {}),
        "task_progress": state.get("task_progress", []) + [{"step": "extract", "tool_name": "extract_text_from_files"}],
    }


def invoice_extract_node(state: AppState) -> AppState:
    res = extract_invoice_fields(state.get("merged_text", ""))
    if not res.success:
        return {
            "invoice": {},
            **_append_error(state, res.error or "extract_invoice_fields 失败"),
            "task_progress": state.get("task_progress", []) + [{"step": "invoice_extract", "tool_name": "extract_invoice_fields"}],
        }
    return {
        "invoice": res.data.get("invoice", {}),
        "task_progress": state.get("task_progress", []) + [{"step": "invoice_extract", "tool_name": "extract_invoice_fields"}],
    }


def activity_parse_node(state: AppState) -> AppState:
    activity_text = str(state.get("payload", {}).get("activity_text", ""))
    res = parse_activity(activity_text)
    if not res.success:
        return {
            "activity": {"description": activity_text.strip()},
            **_append_error(state, res.error or "parse_activity 失败"),
            "task_progress": state.get("task_progress", []) + [{"step": "activity_parse", "tool_name": "parse_activity"}],
        }
    return {
        "activity": res.data.get("activity", {}),
        "task_progress": state.get("task_progress", []) + [{"step": "activity_parse", "tool_name": "parse_activity"}],
    }


def rule_check_node(state: AppState) -> AppState:
    rules = state.get("payload", {}).get("rules", {})
    res = check_rules(state.get("invoice", {}), state.get("activity", {}), rules)
    if not res.success:
        return {
            "rule_result": {"compliance": False, "violations": [res.error or "规则校验失败"], "suggestion": "请人工复核"},
            **_append_error(state, res.error or "check_rules 失败"),
            "task_progress": state.get("task_progress", []) + [{"step": "rule_check", "tool_name": "check_rules"}],
        }
    return {
        "rule_result": res.data,
        "task_progress": state.get("task_progress", []) + [{"step": "rule_check", "tool_name": "check_rules"}],
    }


def gen_doc_node(state: AppState) -> AppState:
    invoice = state.get("invoice", {})
    activity = state.get("activity", {})
    out_dir = state.get("payload", {}).get("output_dir")
    word_res = generate_word_doc(activity, [invoice], out_dir)
    excel_res = generate_excel_sheet([invoice], activity, out_dir)
    errors = list(state.get("errors", []))
    if not word_res.success:
        errors.append(word_res.error or "generate_word_doc 失败")
    if not excel_res.success:
        errors.append(excel_res.error or "generate_excel_sheet 失败")
    return {
        "outputs": {
            **state.get("outputs", {}),
            "word_path": word_res.data.get("word_path", ""),
            "excel_path": excel_res.data.get("excel_path", ""),
        },
        "errors": errors,
        "task_progress": state.get("task_progress", []) + [{"step": "gen_docs", "tool_name": "generate_word_doc/generate_excel_sheet"}],
    }


def gen_mail_node(state: AppState) -> AppState:
    outputs = state.get("outputs", {})
    invoice = state.get("invoice", {})
    draft_res = generate_email_draft(
        activity=state.get("activity", {}),
        summary={"total_amount": invoice.get("amount", 0)},
        attachments=[outputs.get("word_path", ""), outputs.get("excel_path", "")],
    )
    draft = draft_res.data.get("draft", {}) if draft_res.success else {}
    send_res = send_or_export_email(draft, state.get("payload", {}).get("output_dir"))
    errors = list(state.get("errors", []))
    if not draft_res.success:
        errors.append(draft_res.error or "generate_email_draft 失败")
    if not send_res.success:
        errors.append(send_res.error or "send_or_export_email 失败")
    return {
        "email_draft": draft,
        "outputs": {
            **outputs,
            "eml_path": send_res.data.get("eml_path", ""),
        },
        "errors": errors,
        "task_progress": state.get("task_progress", []) + [{"step": "mail", "tool_name": "generate_email_draft/send_or_export_email"}],
    }


def save_record_node(state: AppState) -> AppState:
    record: Dict[str, object] = {
        "invoice": state.get("invoice", {}),
        "activity": state.get("activity", {}),
        "rule_result": state.get("rule_result", {}),
        "outputs": state.get("outputs", {}),
    }
    save_res = save_record(record)
    result = {
        "type": "reimburse",
        "record_id": save_res.data.get("record_id"),
        "outputs": state.get("outputs", {}),
        "rule_result": state.get("rule_result", {}),
        "errors": state.get("errors", []),
    }
    return {
        "result": result,
        "errors": state.get("errors", []) + ([save_res.error] if save_res.error else []),
        "task_progress": state.get("task_progress", []) + [{"step": "save", "tool_name": "save_record"}],
    }


def reimburse_fail_node(state: AppState) -> AppState:
    errors = state.get("errors", [])
    return {
        "result": {
            "type": "reimburse",
            "status": "failed",
            "errors": errors,
            "outputs": state.get("outputs", {}),
        },
        "errors": errors,
        "task_progress": state.get("task_progress", []) + [{"step": "reimburse_fail", "tool_name": "fail_fast_guard"}],
    }
