from __future__ import annotations

import json
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from agent.tools.base import ToolResult, fail, ok


def _ensure_out_dir(output_dir: str | None) -> Path:
    path = Path(output_dir or "docs/parsed/reimburse_outputs").resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def generate_word_doc(activity: Dict[str, Any], invoices: List[Dict[str, Any]], output_dir: str | None = None) -> ToolResult:
    out_dir = _ensure_out_dir(output_dir)
    target = out_dir / f"activity_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
    try:
        from docx import Document
    except Exception:
        return fail("python-docx 不可用")

    doc = Document()
    doc.add_heading("学生活动情况说明", level=1)
    doc.add_paragraph(f"活动日期：{activity.get('activity_date', '')}")
    doc.add_paragraph(f"活动地点：{activity.get('location', '')}")
    doc.add_paragraph(f"活动说明：{activity.get('description', '')}")
    doc.add_paragraph("发票摘要：")
    for inv in invoices:
        doc.add_paragraph(f"- 发票号 {inv.get('invoice_no', '')} 金额 {inv.get('amount', 0)}")
    doc.save(target)
    return ok(word_path=str(target))


def generate_excel_sheet(invoices: List[Dict[str, Any]], activity: Dict[str, Any], output_dir: str | None = None) -> ToolResult:
    out_dir = _ensure_out_dir(output_dir)
    target = out_dir / f"reimburse_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    df = pd.DataFrame(invoices)
    if df.empty:
        df = pd.DataFrame([{"invoice_no": "", "amount": 0.0, "date": ""}])
    df["activity_date"] = activity.get("activity_date", "")
    df.to_excel(target, index=False)
    return ok(excel_path=str(target))


def generate_email_draft(activity: Dict[str, Any], summary: Dict[str, Any], attachments: List[str]) -> ToolResult:
    subject = f"报销材料提交 - {activity.get('activity_date', '')}"
    body = (
        "老师您好，\n\n"
        f"现提交活动报销材料。活动地点：{activity.get('location', '')}。"
        f"报销总金额：{summary.get('total_amount', 0)} 元。\n"
        "附件包含活动说明与报销明细表。\n\n"
        "此致\n敬礼"
    )
    return ok(draft={"subject": subject, "body": body, "attachments": attachments})


def send_or_export_email(draft: Dict[str, Any], output_dir: str | None = None) -> ToolResult:
    out_dir = _ensure_out_dir(output_dir)
    target = out_dir / f"mail_{datetime.now().strftime('%Y%m%d_%H%M%S')}.eml"
    msg = EmailMessage()
    msg["Subject"] = draft.get("subject", "报销材料")
    msg["To"] = ""
    msg["From"] = ""
    payload = {
        "body": draft.get("body", ""),
        "attachments": draft.get("attachments", []),
    }
    msg.set_content(json.dumps(payload, ensure_ascii=False, indent=2))
    target.write_text(msg.as_string(), encoding="utf-8")
    return ok(sent=False, eml_path=str(target), fallback_used=True)
