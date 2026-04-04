from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List

from agent.tools.base import ToolResult, fail, ok


def extract_pdf_text(pdf_path: str) -> ToolResult:
    try:
        import fitz
    except Exception:
        return fail("PyMuPDF 不可用，无法进行 PDF 文本提取", fallback_used=True, text="")

    try:
        doc = fitz.open(pdf_path)
        text = "\n".join(page.get_text("text") for page in doc)
        if not text.strip():
            return fail("PDF 无可提取文本层", fallback_used=True, text="")
        return ok(text=text)
    except Exception as exc:
        return fail(f"PDF 提取失败: {exc}", fallback_used=True, text="")


def ocr_extract(file_path: str) -> ToolResult:
    try:
        from agent.parser.utils.ocr_utils import run_ocr_on_file
    except Exception:
        return fail("OCR 工具不可用", fallback_used=True, text="")

    try:
        result = run_ocr_on_file(file_path)
        text = str(result).strip()
        if not text:
            return fail("OCR 未识别到有效文本", fallback_used=True, text="")
        return ok(text=text)
    except Exception as exc:
        return fail(f"OCR 识别失败: {exc}", fallback_used=True, text="")


def extract_invoice_fields(text: str) -> ToolResult:
    if not text.strip():
        return fail("缺少发票文本")

    amount_match = re.search(r"(\d+(?:\.\d{1,2})?)\s*元", text)
    date_match = re.search(r"(20\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2})", text)
    invoice_no = re.search(r"(?:发票号|发票号码|票据号)[:：]?\s*([A-Za-z0-9-]{6,})", text)

    data = {
        "invoice_no": invoice_no.group(1) if invoice_no else "",
        "amount": float(amount_match.group(1)) if amount_match else 0.0,
        "date": date_match.group(1) if date_match else "",
        "raw_text": text[:4000],
    }
    return ok(invoice=data)


def parse_activity(activity_text: str) -> ToolResult:
    if not activity_text.strip():
        return fail("缺少活动说明文本", fallback_used=True, prompt="请补充活动时间、地点、事由")

    date_match = re.search(r"(20\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2})", activity_text)
    location_match = re.search(r"(?:地点|场地)[:：]?\s*([^，。\n]{2,50})", activity_text)

    info: Dict[str, str] = {
        "activity_date": date_match.group(1) if date_match else "",
        "location": location_match.group(1).strip() if location_match else "",
        "description": activity_text.strip(),
    }
    return ok(activity=info)


def extract_text_from_files(classified: Dict[str, List[str]]) -> ToolResult:
    texts: List[str] = []
    file_text_map: Dict[str, str] = {}

    for pdf in classified.get("pdf", []):
        pdf_res = extract_pdf_text(pdf)
        if pdf_res.success and pdf_res.data.get("text"):
            text = str(pdf_res.data["text"])
            file_text_map[pdf] = text
            texts.append(text)
            continue
        ocr_res = ocr_extract(pdf)
        text = str(ocr_res.data.get("text", ""))
        if text:
            file_text_map[pdf] = text
            texts.append(text)

    for img in classified.get("image", []):
        ocr_res = ocr_extract(img)
        text = str(ocr_res.data.get("text", ""))
        if text:
            file_text_map[img] = text
            texts.append(text)

    for txt in classified.get("text", []):
        try:
            content = Path(txt).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = Path(txt).read_text(encoding="gbk", errors="ignore")
        file_text_map[txt] = content
        texts.append(content)

    return ok(file_text_map=file_text_map, merged_text="\n\n".join(texts))
