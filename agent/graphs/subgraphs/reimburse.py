from __future__ import annotations

from typing import Dict, List

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


def reimburse_start_node(state: AppState) -> AppState:
    return {"task_progress": state.get("task_progress", []) + [{"step": "reimburse_start", "tool_name": "start"}]}


def scan_file_node(state: AppState) -> AppState:
    payload = state.get("payload", {})
    paths: List[str] = list(payload.get("paths", []))
    res = scan_inputs(paths)
    if not res.success:
        return {"errors": state.get("errors", []) + [res.error or "scan_inputs 失败"]}
    return {
        "files": res.data.get("files", []),
        "task_progress": state.get("task_progress", []) + [{"step": "scan", "tool_name": "scan_inputs"}],
    }


def classify_file_node(state: AppState) -> AppState:
    res = classify_files(state.get("files", []))
    return {
        "classified_files": res.data.get("classified", {}),
        "task_progress": state.get("task_progress", []) + [{"step": "classify", "tool_name": "classify_files"}],
    }


def extract_node(state: AppState) -> AppState:
    res = extract_text_from_files(state.get("classified_files", {}))
    return {
        "merged_text": res.data.get("merged_text", ""),
        "file_text_map": res.data.get("file_text_map", {}),
        "task_progress": state.get("task_progress", []) + [{"step": "extract", "tool_name": "extract_text_from_files"}],
    }


def invoice_extract_node(state: AppState) -> AppState:
    res = extract_invoice_fields(state.get("merged_text", ""))
    return {
        "invoice": res.data.get("invoice", {}),
        "task_progress": state.get("task_progress", []) + [{"step": "invoice_extract", "tool_name": "extract_invoice_fields"}],
    }


def activity_parse_node(state: AppState) -> AppState:
    activity_text = str(state.get("payload", {}).get("activity_text", ""))
    res = parse_activity(activity_text)
    return {
        "activity": res.data.get("activity", {}),
        "task_progress": state.get("task_progress", []) + [{"step": "activity_parse", "tool_name": "parse_activity"}],
    }


def rule_check_node(state: AppState) -> AppState:
    rules = state.get("payload", {}).get("rules", {})
    res = check_rules(state.get("invoice", {}), state.get("activity", {}), rules)
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
    return {
        "outputs": {
            **state.get("outputs", {}),
            "word_path": word_res.data.get("word_path", ""),
            "excel_path": excel_res.data.get("excel_path", ""),
        },
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
    send_res = send_or_export_email(draft_res.data.get("draft", {}), state.get("payload", {}).get("output_dir"))
    return {
        "email_draft": draft_res.data.get("draft", {}),
        "outputs": {
            **outputs,
            "eml_path": send_res.data.get("eml_path", ""),
        },
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
    }
    return {
        "result": result,
        "task_progress": state.get("task_progress", []) + [{"step": "save", "tool_name": "save_record"}],
    }
