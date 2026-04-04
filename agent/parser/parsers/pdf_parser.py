"""
agent/parser/parsers/pdf_parser.py

PDF 解析器。
- 文本型 PDF：PyMuPDF 提取文字 + 表格 + 图片
- 扫描型 PDF：检测文字稀疏度 → OCR 降级
- 每页都记录 loc（page 坐标），确保可回溯
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from agent.parser.base import BaseParser
from agent.parser.schema import (
    Error, ImageBlock, Loc, LocType, ParsedDocument, Section,
    TableBlock, TableMeta, Warning,
)
from agent.parser.utils.hash_utils import file_sha1
from agent.parser.utils.file_utils import excel_a1

logger = logging.getLogger(__name__)


class PDFParser(BaseParser):
    supported_extensions = [".pdf"]

    def __init__(
        self,
        ocr_text_ratio_threshold: float = 0.15,
        ocr_dpi: int = 300,
        kb_name: str = "",
    ):
        self.ocr_text_ratio_threshold = ocr_text_ratio_threshold
        self.ocr_dpi = ocr_dpi
        self.kb_name = kb_name

    def parse(self, file_path: str, **kwargs) -> ParsedDocument:
        import fitz  # PyMuPDF

        doc_id = file_sha1(file_path, prefix=self.kb_name)
        fpath = Path(file_path)
        warnings: list[Warning] = []
        errors: list[Error] = []

        try:
            pdf = fitz.open(file_path)
        except Exception as exc:
            return ParsedDocument(
                doc_id=doc_id,
                source=self._source_dict(fpath),
                content_type="pdf",
                errors=[Error(
                    error_code="PDF_OPEN_FAILED",
                    message=str(exc),
                    loc=Loc(type=LocType.PAGE.value, value=0),
                )],
            )

        total_pages = len(pdf)
        pages_text: list[str] = []             # 每页的原始文本
        all_tables: list[TableBlock] = []
        all_images: list[ImageBlock] = []
        pages_with_text = 0

        # ---- 逐页提取 ----
        for page_num in range(total_pages):
            page = pdf[page_num]
            text = page.get_text("text") or ""
            if text.strip():
                pages_with_text += 1
            pages_text.append(text)

            # 表格提取（PyMuPDF 4.x+）
            try:
                found_tables = page.find_tables()
                for ti, tab in enumerate(found_tables):
                    data = tab.extract()
                    if not data:
                        continue
                    table_id = f"p{page_num+1}_t{ti+1}"
                    headers = [str(c) if c else f"col_{ci}" for ci, c in enumerate(data[0])]
                    rows = data[1:] if len(data) > 1 else []
                    # 坐标映射（简化：行号 → 页码）
                    coord_map = {}
                    for ri in range(len(rows)):
                        for ci in range(len(headers)):
                            coord_map[f"{ri},{ci}"] = f"page{page_num+1}"
                    all_tables.append(TableBlock(
                        meta=TableMeta(
                            table_id=table_id,
                            source_sheet=f"page{page_num+1}",
                            source_range=f"page{page_num+1}",
                            row_count=len(rows),
                            col_count=len(headers),
                            coord_map=coord_map,
                        ),
                        headers=headers,
                        rows=rows,
                    ))
            except Exception as exc:
                warnings.append(Warning(
                    code="TABLE_EXTRACT_FAILED",
                    message=f"Page {page_num+1} table extraction failed: {exc}",
                    loc=Loc(type=LocType.PAGE.value, value=page_num + 1),
                ))

            # 图片提取
            try:
                for img_idx, img_info in enumerate(page.get_images(full=True)):
                    xref = img_info[0]
                    all_images.append(ImageBlock(
                        image_id=f"p{page_num+1}_img{img_idx+1}",
                        loc=Loc(type=LocType.PAGE.value, value=page_num + 1,
                                extra={"xref": xref}),
                    ))
            except Exception:
                pass

        # ---- 判断是否需要 OCR ----
        text_ratio = pages_with_text / total_pages if total_pages > 0 else 0
        is_scanned = text_ratio < self.ocr_text_ratio_threshold

        if is_scanned:
            warnings.append(Warning(
                code="SCANNED_PDF_OCR_FALLBACK",
                message=(
                    f"Text found on {pages_with_text}/{total_pages} pages "
                    f"(ratio={text_ratio:.2f}). Falling back to OCR."
                ),
                loc=Loc(type=LocType.PAGE.value, value=0),
            ))
            pages_text = self._ocr_all_pages(pdf, errors, warnings)

        pdf.close()

        # ---- 构建 sections（按页 + 启发式标题检测）----
        sections = self._build_sections(pages_text)

        # ---- 组装 ParsedDocument ----
        title = self._detect_title(pages_text)

        return ParsedDocument(
            doc_id=doc_id,
            source=self._source_dict(fpath),
            title=title,
            content_type="pdf",
            sections=sections,
            tables=all_tables,
            images=all_images,
            warnings=warnings,
            errors=errors,
            metadata={
                "total_pages": total_pages,
                "text_ratio": round(text_ratio, 3),
                "is_scanned": is_scanned,
                "pages_with_text": pages_with_text,
            },
        )

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------
    def _source_dict(self, fpath: Path) -> dict:
        return {
            "file_name": fpath.name,
            "file_type": "pdf",
            "file_size_bytes": fpath.stat().st_size,
            "file_path": str(fpath),
        }

    def _ocr_all_pages(
        self, pdf, errors: list[Error], warnings: list[Warning]
    ) -> list[str]:
        """逐页渲染为图片 → OCR"""
        from agent.parser.utils.ocr_utils import run_ocr

        pages_text = []
        for page_num in range(len(pdf)):
            try:
                pix = pdf[page_num].get_pixmap(dpi=self.ocr_dpi)
                img_bytes = pix.tobytes("png")
                text = run_ocr(img_bytes)
                pages_text.append(text)
            except Exception as exc:
                pages_text.append("")
                errors.append(Error(
                    error_code="OCR_PAGE_FAILED",
                    message=f"Page {page_num+1} OCR failed: {exc}",
                    loc=Loc(type=LocType.PAGE.value, value=page_num + 1),
                ))
        return pages_text

    def _build_sections(self, pages_text: list[str]) -> list[Section]:
        """从逐页文本构建 sections"""
        sections: list[Section] = []
        current_heading = ""
        current_level = 1
        current_content_lines: list[str] = []
        current_page = 1

        for page_num, text in enumerate(pages_text):
            lines = text.split("\n")
            for line in lines:
                stripped = line.strip()
                if not stripped:
                    current_content_lines.append("")
                    continue

                detected_level = self._detect_heading_level(stripped)
                if detected_level is not None:
                    # 保存上一个 section
                    if current_heading or current_content_lines:
                        sections.append(Section(
                            heading=current_heading,
                            level=current_level,
                            content="\n".join(current_content_lines).strip(),
                            loc=Loc(type=LocType.PAGE.value, value=current_page),
                        ))
                    current_heading = stripped
                    current_level = detected_level
                    current_content_lines = []
                    current_page = page_num + 1
                else:
                    current_content_lines.append(stripped)

        # 保存最后一个 section
        if current_heading or current_content_lines:
            sections.append(Section(
                heading=current_heading,
                level=current_level,
                content="\n".join(current_content_lines).strip(),
                loc=Loc(type=LocType.PAGE.value, value=current_page),
            ))

        return sections

    @staticmethod
    def _detect_heading_level(line: str) -> int | None:
        """
        简易启发式标题检测：
        - "第X章" → level 1
        - "第X节" / "X.Y" 开头的短行 → level 2
        - "X.Y.Z" 开头 → level 3
        - 短行 + 无句末标点 → level 2
        """
        if not line or len(line) > 60:
            return None
        if re.match(r'^第[一二三四五六七八九十\d]+章', line):
            return 1
        if re.match(r'^第[一二三四五六七八九十\d]+节', line):
            return 2
        if re.match(r'^\d+\.\d+\.\d+', line):
            return 3
        if re.match(r'^\d+\.\d+\s', line):
            return 2
        if re.match(r'^\d+\s', line) and len(line) < 30:
            return 2
        # 短行无标点 → 可能是标题
        if (len(line) < 40
                and not line.endswith(("。", ".", "，", ",", "；", ";", "：", ":", "、"))):
            # 进一步检查：全大写 / 加粗标记等
            if re.match(r'^[A-Z\s]{5,}$', line):
                return 2
        return None

    @staticmethod
    def _detect_title(pages_text: list[str]) -> str:
        """从第一页提取标题（取第一个非空行）"""
        if not pages_text:
            return ""
        for line in pages_text[0].split("\n"):
            stripped = line.strip()
            if stripped and len(stripped) < 80:
                return stripped
        return ""