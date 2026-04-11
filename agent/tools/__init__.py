from __future__ import annotations

from importlib import import_module
from typing import Any, Dict, Tuple

__all__ = [
    "scan_inputs",
    "classify_files",
    "extract_pdf_text",
    "ocr_extract",
    "extract_text_from_files",
    "extract_invoice_fields",
    "parse_activity",
    "check_rules",
    "rule_retrieve",
    "rag_retrieve",
    "generate_word_doc",
    "generate_excel_sheet",
    "generate_email_draft",
    "send_or_export_email",
    "save_record",
    "load_records",
    "data_clean",
    "aggregate_records",
    "generate_final_account",
    "load_final_data",
    "budget_calculate",
    "generate_budget",
    "generate_report",
    "question_understand",
    "answer_generate",
    "build_workflow_hint",
]


_LAZY_EXPORTS: Dict[str, Tuple[str, str]] = {
    "scan_inputs": ("agent.tools.input_tools", "scan_inputs"),
    "classify_files": ("agent.tools.input_tools", "classify_files"),
    "extract_pdf_text": ("agent.tools.extraction_tools", "extract_pdf_text"),
    "ocr_extract": ("agent.tools.extraction_tools", "ocr_extract"),
    "extract_text_from_files": ("agent.tools.extraction_tools", "extract_text_from_files"),
    "extract_invoice_fields": ("agent.tools.extraction_tools", "extract_invoice_fields"),
    "parse_activity": ("agent.tools.extraction_tools", "parse_activity"),
    "check_rules": ("agent.tools.rule_tools", "check_rules"),
    "rule_retrieve": ("agent.tools.rule_tools", "rule_retrieve"),
    "rag_retrieve": ("agent.tools.rule_tools", "rag_retrieve"),
    "generate_word_doc": ("agent.tools.doc_tools", "generate_word_doc"),
    "generate_excel_sheet": ("agent.tools.doc_tools", "generate_excel_sheet"),
    "generate_email_draft": ("agent.tools.doc_tools", "generate_email_draft"),
    "send_or_export_email": ("agent.tools.doc_tools", "send_or_export_email"),
    "save_record": ("agent.tools.storage_tools", "save_record"),
    "load_records": ("agent.tools.storage_tools", "load_records"),
    "data_clean": ("agent.tools.stats_tools", "data_clean"),
    "aggregate_records": ("agent.tools.stats_tools", "aggregate_records"),
    "generate_final_account": ("agent.tools.stats_tools", "generate_final_account"),
    "load_final_data": ("agent.tools.stats_tools", "load_final_data"),
    "budget_calculate": ("agent.tools.stats_tools", "budget_calculate"),
    "generate_budget": ("agent.tools.stats_tools", "generate_budget"),
    "generate_report": ("agent.tools.stats_tools", "generate_report"),
    "question_understand": ("agent.tools.qa_tools", "question_understand"),
    "answer_generate": ("agent.tools.qa_tools", "answer_generate"),
    "build_workflow_hint": ("agent.tools.qa_tools", "build_workflow_hint"),
}


def __getattr__(name: str) -> Any:
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module 'agent.tools' has no attribute '{name}'")
    module_name, attr_name = target
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(list(globals().keys()) + __all__))
