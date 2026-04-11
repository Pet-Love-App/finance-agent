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
        "reimburse_stop_on_violation",
        False,
        legacy_keys=("stop_on_rule_violation",),
    )
    rule_result = state.get("rule_result", {})
    compliance = bool(rule_result.get("compliance", False))
    
    if stop_on_violation and not compliance:
        return "SaveRecordNode"
    return "CollectInfoNode"


def route_after_collect_info(state: AppState) -> str:
    """信息收集后的路由"""
    # 如果有缺失字段，暂时直接生成文档（后续可添加对话功能）
    if state.get("missing_fields"):
        return "GenDocNode"  # 暂时跳过对话，直接生成文档
    # 没有缺失字段，继续生成文档
    return "GenDocNode"


def reimburse_start_node(state: AppState) -> AppState:
    print("\n=== reimburse_start_node 状态 ===")
    print(f"  task_type: {state.get('task_type')}")
    print(f"  payload: {state.get('payload', {}).keys()}")
    print(f"  invoices: {state.get('invoices', [])}")
    print(f"  total_amount: {state.get('total_amount', 0.0)}")
    print(f"  errors: {state.get('errors', [])}")
    return {
        **state,
        "task_progress": state.get("task_progress", []) + [{"step": "reimburse_start", "tool_name": "start"}]
    }


def scan_file_node(state: AppState) -> AppState:
    print("\n=== scan_file_node 状态 ===")
    print(f"  task_type: {state.get('task_type')}")
    print(f"  payload: {state.get('payload', {}).keys()}")
    print(f"  invoices: {state.get('invoices', [])}")
    print(f"  total_amount: {state.get('total_amount', 0.0)}")
    print(f"  errors: {state.get('errors', [])}")
    
    payload = state.get("payload", {})
    paths: List[str] = list(payload.get("paths", []))
    res = scan_inputs(paths)
    if not res.success:
        return {
            **state,
            "errors": state.get("errors", []) + [res.error or "scan_inputs 失败"],
            "task_progress": state.get("task_progress", []) + [{"step": "scan", "tool_name": "scan_inputs"}],
        }
    return {
        **state,
        "files": res.data.get("files", []),
        "task_progress": state.get("task_progress", []) + [{"step": "scan", "tool_name": "scan_inputs"}],
    }


def classify_file_node(state: AppState) -> AppState:
    print("\n=== classify_file_node 状态 ===")
    print(f"  task_type: {state.get('task_type')}")
    print(f"  files: {state.get('files', [])}")
    print(f"  invoices: {state.get('invoices', [])}")
    print(f"  total_amount: {state.get('total_amount', 0.0)}")
    print(f"  errors: {state.get('errors', [])}")
    
    res = classify_files(state.get("files", []))
    if not res.success:
        return {
            **state,
            "errors": state.get("errors", []) + [res.error or "classify_files 失败"],
            "task_progress": state.get("task_progress", []) + [{"step": "classify", "tool_name": "classify_files"}],
        }
    return {
        **state,
        "classified_files": res.data.get("classified", {}),
        "task_progress": state.get("task_progress", []) + [{"step": "classify", "tool_name": "classify_files"}],
    }


def extract_node(state: AppState) -> AppState:
    print("\n=== extract_node 状态 ===")
    print(f"  task_type: {state.get('task_type')}")
    print(f"  classified_files: {state.get('classified_files', {})}")
    print(f"  invoices: {state.get('invoices', [])}")
    print(f"  total_amount: {state.get('total_amount', 0.0)}")
    print(f"  errors: {state.get('errors', [])}")
    
    res = extract_text_from_files(state.get("classified_files", {}))
    if not res.success:
        return {
            **state,
            "errors": state.get("errors", []) + [res.error or "extract_text_from_files 失败"],
            "task_progress": state.get("task_progress", []) + [{"step": "extract", "tool_name": "extract_text_from_files"}],
        }
    return {
        **state,
        "merged_text": res.data.get("merged_text", ""),
        "file_text_map": res.data.get("file_text_map", {}),
        "task_progress": state.get("task_progress", []) + [{"step": "extract", "tool_name": "extract_text_from_files"}],
    }


def invoice_extract_node(state: AppState) -> AppState:
    print("\n=== invoice_extract_node 状态 ===")
    print(f"  task_type: {state.get('task_type')}")
    print(f"  file_text_map: {state.get('file_text_map', {}).keys()}")
    print(f"  invoices: {state.get('invoices', [])}")
    print(f"  total_amount: {state.get('total_amount', 0.0)}")
    print(f"  errors: {state.get('errors', [])}")
    
    file_text_map = state.get("file_text_map", {})
    invoices = []
    total_amount = 0.0
    
    print("\n=== 发票提取调试信息 ===")
    print(f"文件数量: {len(file_text_map)}")
    
    # 处理每个文件的文本
    for file_path, text in file_text_map.items():
        print(f"\n处理文件: {file_path}")
        print(f"  文本长度: {len(text)}")
        if text and "[OCR ERROR" not in text:
            res = extract_invoice_fields(text)
            print(f"  提取结果: {'成功' if res.success else '失败'}")
            if res.success:
                invoice = res.data.get("invoice", {})
                print(f"  提取到发票: {bool(invoice)}")
                if invoice:
                    try:
                        print(f"  发票信息: {invoice}")
                    except UnicodeEncodeError:
                        # 处理编码错误，只打印金额等关键信息
                        print(f"  发票信息: {{'amount': {invoice.get('amount', 0)}, 'invoice_no': {invoice.get('invoice_no', '')}, 'date': {invoice.get('date', '')}, 'content': {invoice.get('content', '')}}}")
                    invoices.append(invoice)
                    # 累加金额
                    amount = invoice.get("amount", 0)
                    if isinstance(amount, (int, float)):
                        total_amount += amount
                        print(f"  累加金额: {amount}, 总计: {total_amount}")
        else:
            print("  跳过: 文本为空或包含 OCR 错误")
    
    # 如果没有提取到发票，使用合并文本再尝试一次
    if not invoices:
        merged_text = state.get("merged_text", "")
        print(f"\n未从单个文件提取到发票，尝试使用合并文本")
        print(f"  合并文本长度: {len(merged_text)}")
        res = extract_invoice_fields(merged_text)
        print(f"  提取结果: {'成功' if res.success else '失败'}")
        if res.success:
            invoice = res.data.get("invoice", {})
            print(f"  提取到发票: {bool(invoice)}")
            if invoice:
                    try:
                        print(f"  发票信息: {invoice}")
                    except UnicodeEncodeError:
                        # 处理编码错误，只打印金额等关键信息
                        print(f"  发票信息: {{'amount': {invoice.get('amount', 0)}, 'invoice_no': {invoice.get('invoice_no', '')}, 'date': {invoice.get('date', '')}, 'content': {invoice.get('content', '')}}}")
                    invoices.append(invoice)
                    amount = invoice.get("amount", 0)
                    if isinstance(amount, (int, float)):
                        total_amount += amount
                        print(f"  累加金额: {amount}, 总计: {total_amount}")
    
    # 计算总计
    print(f"\n最终结果:")
    print(f"  提取到的发票数量: {len(invoices)}")
    print(f"  总金额: {total_amount}")
    print("=== 发票提取调试信息结束 ===")
    
    if invoices:
        return {
            **state,
            "invoices": invoices,  # 多个发票
            "invoice": invoices[0],  # 保持向后兼容，使用第一个发票
            "total_amount": total_amount,  # 总计金额
            "task_progress": state.get("task_progress", []) + [{"step": "invoice_extract", "tool_name": "extract_invoice_fields"}],
        }
    else:
        return {
            **state,
            "invoices": [],
            "invoice": {},
            "total_amount": 0.0,
            "errors": state.get("errors", []) + ["未提取到发票信息"],
            "task_progress": state.get("task_progress", []) + [{"step": "invoice_extract", "tool_name": "extract_invoice_fields"}],
        }


def activity_parse_node(state: AppState) -> AppState:
    print("\n=== activity_parse_node 状态 ===")
    print(f"  task_type: {state.get('task_type')}")
    try:
        print(f"  activity_text: {state.get('payload', {}).get('activity_text', '')}")
    except UnicodeEncodeError:
        print(f"  activity_text: 无法打印（包含非ASCII字符）")
    try:
        print(f"  invoices: {state.get('invoices', [])}")
    except UnicodeEncodeError:
        print(f"  invoices: 无法打印（包含非ASCII字符）")
    print(f"  total_amount: {state.get('total_amount', 0.0)}")
    print(f"  errors: {state.get('errors', [])}")
    
    activity_text = str(state.get("payload", {}).get("activity_text", ""))
    res = parse_activity(activity_text)
    if not res.success:
        return {
            **state,
            "activity": {"description": activity_text.strip()},
            "errors": state.get("errors", []) + [res.error or "parse_activity 失败"],
            "task_progress": state.get("task_progress", []) + [{"step": "activity_parse", "tool_name": "parse_activity"}],
        }
    return {
        **state,
        "activity": res.data.get("activity", {}),
        "task_progress": state.get("task_progress", []) + [{"step": "activity_parse", "tool_name": "parse_activity"}],
    }


def rule_check_node(state: AppState) -> AppState:
    print("\n=== rule_check_node 状态 ===")
    print(f"  task_type: {state.get('task_type')}")
    try:
        print(f"  invoice: {state.get('invoice', {})}")
    except UnicodeEncodeError:
        invoice = state.get('invoice', {})
        print(f"  invoice: {{'amount': {invoice.get('amount', 0)}, 'invoice_no': {invoice.get('invoice_no', '')}, 'date': {invoice.get('date', '')}, 'content': {invoice.get('content', '')}}}")
    try:
        print(f"  activity: {state.get('activity', {})}")
    except UnicodeEncodeError:
        print(f"  activity: 无法打印（包含非ASCII字符）")
    try:
        print(f"  invoices: {state.get('invoices', [])}")
    except UnicodeEncodeError:
        print(f"  invoices: 无法打印（包含非ASCII字符）")
    print(f"  total_amount: {state.get('total_amount', 0.0)}")
    print(f"  errors: {state.get('errors', [])}")
    
    rules = state.get("payload", {}).get("rules", {})
    res = check_rules(state.get("invoice", {}), state.get("activity", {}), rules)
    if not res.success:
        return {
            **state,
            "rule_result": {"compliance": False, "violations": [res.error or "规则校验失败"], "suggestion": "请人工复核"},
            "errors": state.get("errors", []) + [res.error or "check_rules 失败"],
            "task_progress": state.get("task_progress", []) + [{"step": "rule_check", "tool_name": "check_rules"}],
        }
    return {
        **state,
        "rule_result": res.data,
        "task_progress": state.get("task_progress", []) + [{"step": "rule_check", "tool_name": "check_rules"}],
    }


def collect_info_node(state: AppState) -> AppState:
    print("\n=== collect_info_node 状态 ===")
    print(f"  task_type: {state.get('task_type')}")
    try:
        print(f"  activity: {state.get('activity', {})}")
    except UnicodeEncodeError:
        print(f"  activity: 无法打印（包含非ASCII字符）")
    try:
        print(f"  invoice: {state.get('invoice', {})}")
    except UnicodeEncodeError:
        invoice = state.get('invoice', {})
        print(f"  invoice: {{'amount': {invoice.get('amount', 0)}, 'invoice_no': {invoice.get('invoice_no', '')}, 'date': {invoice.get('date', '')}, 'content': {invoice.get('content', '')}}}")
    try:
        print(f"  invoices: {state.get('invoices', [])}")
    except UnicodeEncodeError:
        print(f"  invoices: 无法打印（包含非ASCII字符）")
    print(f"  total_amount: {state.get('total_amount', 0.0)}")
    print(f"  errors: {state.get('errors', [])}")
    
    """信息收集节点，检查并收集缺失的信息"""
    activity = state.get("activity", {})
    invoice = state.get("invoice", {})
    
    # 检查缺失的字段
    missing_fields = []
    
    # 检查 activity 字段
    required_activity_fields = [
        ("student_name", "经办同学姓名"),
        ("contact", "联系方式"),
        ("participants", "参与人员"),
        ("organization", "归属（学生组织）")
    ]
    
    for field, label in required_activity_fields:
        if not activity.get(field):
            missing_fields.append({"type": "activity", "field": field, "label": label})
    
    # 检查 invoice 字段
    required_invoice_fields = [
        ("invoice_no", "发票号码"),
        ("amount", "发票金额"),
        ("date", "发票日期"),
        ("content", "发票内容")
    ]
    
    for field, label in required_invoice_fields:
        if not invoice.get(field):
            missing_fields.append({"type": "invoice", "field": field, "label": label})
    
    # 如果有缺失字段，需要进行对话
    if missing_fields:
        return {
            **state,
            "missing_fields": missing_fields,
            "task_progress": state.get("task_progress", []) + [{"step": "collect_info", "tool_name": "info_collection"}],
        }
    
    # 没有缺失字段，继续流程
    return {
        **state,
        "task_progress": state.get("task_progress", []) + [{"step": "collect_info", "tool_name": "info_collection"}],
    }


def gen_doc_node(state: AppState) -> AppState:
    print("\n=== gen_doc_node 状态 ===")
    print(f"  task_type: {state.get('task_type')}")
    try:
        print(f"  invoices: {state.get('invoices', [])}")
    except UnicodeEncodeError:
        print(f"  invoices: 无法打印（包含非ASCII字符）")
    try:
        print(f"  activity: {state.get('activity', {})}")
    except UnicodeEncodeError:
        print(f"  activity: 无法打印（包含非ASCII字符）")
    print(f"  total_amount: {state.get('total_amount', 0.0)}")
    print(f"  errors: {state.get('errors', [])}")
    
    invoices = state.get("invoices", [])
    activity = state.get("activity", {})
    out_dir = state.get("payload", {}).get("output_dir")
    total_amount = state.get("total_amount", 0.0)
    
    # 增强 activity 数据，添加模板需要的字段
    enhanced_activity = {
        **activity,
        "activity_content": activity.get("description", ""),
        "activity_location": activity.get("location", ""),
        "name": activity.get("student_name", ""),
        "participants": activity.get("participants", ""),
        "contact": activity.get("contact", ""),
        "activity_time": activity.get("activity_date", ""),
        "expense_detail": f"总金额: {total_amount} 元",
        "activity_name": activity.get("description", ""),
        "org": activity.get("organization", ""),
        "student_name": activity.get("student_name", ""),
        "student_id": activity.get("student_id", "")
    }
    
    # 增强所有发票数据，添加模板需要的字段
    enhanced_invoices = []
    for invoice in invoices:
        enhanced_invoice = {
            **invoice,
            "invoice_serial": invoice.get("invoice_no", ""),
            "invoice_amount": invoice.get("amount", 0),
            "invoice_date": invoice.get("date", ""),
            "invoice_content": invoice.get("content", ""),
            "activity_name": activity.get("description", ""),
            "activity_date": activity.get("activity_date", ""),
            "organization": activity.get("organization", ""),
            "handler_name": activity.get("student_name", ""),
            "student_id": activity.get("student_id", "")
        }
        enhanced_invoices.append(enhanced_invoice)
    
    # 如果没有发票，使用空列表
    if not enhanced_invoices:
        enhanced_invoices = []
    
    # 使用指定的模板
    word_template = "学生活动经费使用情况.docx"
    excel_template = "学生活动经费报销明细模板.xlsx"
    
    word_res = generate_word_doc(enhanced_activity, enhanced_invoices, out_dir, template_name=word_template)
    excel_res = generate_excel_sheet(enhanced_invoices, enhanced_activity, out_dir, template_name=excel_template)
    errors = list(state.get("errors", []))
    if not word_res.success:
        errors.append(word_res.error or "generate_word_doc 失败")
    if not excel_res.success:
        errors.append(excel_res.error or "generate_excel_sheet 失败")
    return {
        **state,
        "outputs": {
            **state.get("outputs", {}),
            "word_path": word_res.data.get("word_path", ""),
            "excel_path": excel_res.data.get("excel_path", ""),
        },
        "errors": errors,
        "task_progress": state.get("task_progress", []) + [{"step": "gen_docs", "tool_name": "generate_word_doc/generate_excel_sheet"}],
    }


def gen_mail_node(state: AppState) -> AppState:
    print("\n=== gen_mail_node 状态 ===")
    print(f"  task_type: {state.get('task_type')}")
    print(f"  outputs: {state.get('outputs', {})}")
    try:
        print(f"  invoices: {state.get('invoices', [])}")
    except UnicodeEncodeError:
        print(f"  invoices: 无法打印（包含非ASCII字符）")
    print(f"  total_amount: {state.get('total_amount', 0.0)}")
    print(f"  errors: {state.get('errors', [])}")
    
    outputs = state.get("outputs", {})
    total_amount = state.get("total_amount", 0.0)
    draft_res = generate_email_draft(
        activity=state.get("activity", {}),
        summary={"total_amount": total_amount},
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
        **state,
        "email_draft": draft,
        "outputs": {
            **outputs,
            "eml_path": send_res.data.get("eml_path", ""),
        },
        "errors": errors,
        "task_progress": state.get("task_progress", []) + [{"step": "mail", "tool_name": "generate_email_draft/send_or_export_email"}],
    }


def save_record_node(state: AppState) -> AppState:
    print("\n=== save_record_node 状态 ===")
    print(f"  task_type: {state.get('task_type')}")
    try:
        print(f"  invoice: {state.get('invoice', {})}")
    except UnicodeEncodeError:
        invoice = state.get('invoice', {})
        print(f"  invoice: {{'amount': {invoice.get('amount', 0)}, 'invoice_no': {invoice.get('invoice_no', '')}, 'date': {invoice.get('date', '')}, 'content': {invoice.get('content', '')}}}")
    try:
        print(f"  invoices: {state.get('invoices', [])}")
    except UnicodeEncodeError:
        print(f"  invoices: 无法打印（包含非ASCII字符）")
    print(f"  total_amount: {state.get('total_amount', 0.0)}")
    print(f"  outputs: {state.get('outputs', {})}")
    print(f"  errors: {state.get('errors', [])}")
    
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
        "invoices": state.get("invoices", []),
        "total_amount": state.get("total_amount", 0.0),
    }
    return {
        **state,
        "result": result,
        "errors": state.get("errors", []) + ([save_res.error] if save_res.error else []),
        "task_progress": state.get("task_progress", []) + [{"step": "save", "tool_name": "save_record"}],
    }


def reimburse_fail_node(state: AppState) -> AppState:
    errors = state.get("errors", [])
    return {
        **state,
        "result": {
            "type": "reimburse",
            "status": "failed",
            "errors": errors,
            "outputs": state.get("outputs", {}),
        },
        "errors": errors,
        "task_progress": state.get("task_progress", []) + [{"step": "reimburse_fail", "tool_name": "fail_fast_guard"}],
    }
