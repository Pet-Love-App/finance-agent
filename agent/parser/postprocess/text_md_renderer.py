"""
agent/parser/postprocess/text_md_renderer.py

从 ParsedDocument 结构化内容渲染 text.md。
BOO-63 核心要求：
- 顶部元信息块（5-10行，溯源，不影响检索）
- Word/PDF：保持标题层级与条款编号
- PPT：按 Slide 输出 [Slide N] 标题 + bullets + notes
- Excel：按表块输出 [Table <id>] Sheet=<name> Range=<range>，
         行内容用 "列名: 值" 串联
- 表格每 20-50 行一段
- 不得包含解析器猜测/补全内容（猜测只在 warnings）
- 低噪声：无重复页眉页脚、空行堆叠
"""
from __future__ import annotations

import re
from typing import Any

from agent.parser.schema import ParsedDocument, Section, SlideContent, TableBlock


class TextMdRenderer:
    """将 ParsedDocument 渲染为 text.md"""

    def __init__(self, table_rows_per_chunk: int = 30):
        self.table_rows_per_chunk = table_rows_per_chunk

    def render(self, doc: ParsedDocument) -> str:
        parts: list[str] = []

        # ---- 顶部元信息块 ----
        parts.append(self._render_header(doc))

        # ---- 按内容类型渲染正文 ----
        if doc.content_type == "pptx":
            parts.append(self._render_slides(doc.slides))
        elif doc.content_type == "excel":
            parts.append(self._render_tables(doc.tables))
        else:
            # Word / PDF：按 sections
            parts.append(self._render_sections(doc.sections))
            # 附带表格（如果有）
            if doc.tables:
                parts.append("\n---\n")
                parts.append(self._render_tables(doc.tables))

        # ---- 清洗 ----
        result = "\n\n".join(p for p in parts if p.strip())
        result = self._clean(result)
        return result

    # ------------------------------------------------------------------
    # 元信息头
    # ------------------------------------------------------------------
    def _render_header(self, doc: ParsedDocument) -> str:
        lines = []
        if doc.title:
            lines.append(f"# {doc.title}")
        source = doc.source
        meta_parts = []
        if source.get("file_name"):
            meta_parts.append(f"来源文件: {source['file_name']}")
        if source.get("file_path"):
            meta_parts.append(f"原始路径: {source['file_path']}")
        if doc.metadata.get("total_pages"):
            meta_parts.append(f"页数: {doc.metadata['total_pages']}")
        if doc.metadata.get("total_slides"):
            meta_parts.append(f"幻灯片数: {doc.metadata['total_slides']}")
        if doc.metadata.get("sheet_names"):
            meta_parts.append(f"Sheet: {', '.join(doc.metadata['sheet_names'])}")
        if meta_parts:
            lines.append("  \n".join(meta_parts))
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Sections（Word / PDF）
    # ------------------------------------------------------------------
    def _render_sections(self, sections: list[Section]) -> str:
        if not sections:
            return ""
        parts = []
        for sec in sections:
            if sec.heading:
                prefix = "#" * min(sec.level, 6)
                parts.append(f"{prefix} {sec.heading}")
            if sec.content:
                parts.append(sec.content)
            parts.append("")  # 段落间空行
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Slides（PPT）
    # ------------------------------------------------------------------
    def _render_slides(self, slides: list[SlideContent]) -> str:
        """
        BOO-63 格式：
        [Slide N] 标题
        - bullet1
        - bullet2
        > Notes: ...
        """
        if not slides:
            return ""
        parts = []
        for slide in slides:
            header = f"## [Slide {slide.slide_number}] {slide.title}"
            parts.append(header)

            if slide.bullets:
                for b in slide.bullets:
                    parts.append(f"- {b}")

            if slide.text_blocks:
                for tb in slide.text_blocks:
                    parts.append(tb)

            if slide.notes:
                parts.append(f"\n> Notes: {slide.notes}")

            # Slide 内表格
            if slide.tables:
                for t in slide.tables:
                    parts.append(self._render_single_table(t))

            parts.append("")  # 段落间空行

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Tables（Excel / 通用）
    # ------------------------------------------------------------------
    def _render_tables(self, tables: list[TableBlock]) -> str:
        if not tables:
            return ""
        parts = []
        for t in tables:
            parts.append(self._render_single_table(t))
            parts.append("")
        return "\n".join(parts)

    def _render_single_table(self, t: TableBlock) -> str:
        """
        BOO-63 格式：
        [Table <table_id>] Sheet=<name> Range=<range>
        然后逐行用 "列名: 值" 串联
        每 N 行一段
        """
        parts = []
        # 表头
        meta = t.meta
        header_line = f"### [Table {meta.table_id}]"
        if meta.source_sheet:
            header_line += f" Sheet={meta.source_sheet}"
        if meta.source_range:
            header_line += f" Range={meta.source_range}"
        parts.append(header_line)

        if not t.rows:
            parts.append("（空表）")
            return "\n".join(parts)

        # 先输出表头说明
        parts.append(f"列: {' | '.join(t.headers)}")
        parts.append("")

        # 逐行转写
        for chunk_start in range(0, len(t.rows), self.table_rows_per_chunk):
            chunk_end = min(chunk_start + self.table_rows_per_chunk, len(t.rows))
            for ri in range(chunk_start, chunk_end):
                row = t.rows[ri]
                # "列名: 值" 串联
                pairs = []
                for ci, h in enumerate(t.headers):
                    val = row[ci] if ci < len(row) else ""
                    if val is None:
                        val = ""
                    val_str = str(val).strip()
                    if val_str:
                        pairs.append(f"{h}: {val_str}")
                row_text = f"[Row {ri+1}] {'; '.join(pairs)}"
                parts.append(row_text)

            # 段间空行
            if chunk_end < len(t.rows):
                parts.append("")

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # 清洗
    # ------------------------------------------------------------------
    @staticmethod
    def _clean(text: str) -> str:
        # 去掉连续空行（最多保留 2 个）
        text = re.sub(r'\n{3,}', '\n\n', text)
        # 去掉行末空格
        text = re.sub(r'[ \t]+\n', '\n', text)
        return text.strip()