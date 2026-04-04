"""
agent/parser/parsers/md_parser.py

Markdown 解析器。
- 按标题层级切分 sections
- 提取 Markdown 表格 → TableBlock（含坐标映射到行号）
- 提取 YAML front-matter 元数据
- 检测图片引用（本地图片发 warning 提示需 OCR）
- 每个段落/标题记录 loc（行号）
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Optional

from agent.parser.base import BaseParser
from agent.parser.schema import (
    Error, ImageBlock, Loc, LocType, ParsedDocument, Section,
    TableBlock, TableMeta, Warning,
)
from agent.parser.utils.hash_utils import file_sha1
from agent.parser.utils.file_utils import detect_encoding

logger = logging.getLogger(__name__)


class MarkdownParser(BaseParser):
    supported_extensions = [".md", ".markdown", ".txt"]

    def __init__(self, kb_name: str = ""):
        self.kb_name = kb_name

    def parse(self, file_path: str, **kwargs) -> ParsedDocument:
        doc_id = file_sha1(file_path, prefix=self.kb_name)
        fpath = Path(file_path)
        warnings: list[Warning] = []
        errors: list[Error] = []

        # ---- 读取文件 ----
        try:
            encoding = detect_encoding(file_path)
            text = fpath.read_text(encoding=encoding)
        except UnicodeDecodeError:
            try:
                text = fpath.read_text(encoding="utf-8", errors="replace")
                warnings.append(Warning(
                    code="ENCODING_FALLBACK",
                    message=f"File encoding issue, decoded with utf-8 replace mode.",
                    loc=Loc(type=LocType.LINE.value, value=1),
                ))
            except Exception as exc:
                return ParsedDocument(
                    doc_id=doc_id,
                    source=self._source_dict(fpath),
                    content_type="markdown",
                    errors=[Error(
                        error_code="FILE_READ_FAILED",
                        message=str(exc),
                        loc=Loc(type=LocType.LINE.value, value=0),
                    )],
                )
        except Exception as exc:
            return ParsedDocument(
                doc_id=doc_id,
                source=self._source_dict(fpath),
                content_type="markdown",
                errors=[Error(
                    error_code="FILE_READ_FAILED",
                    message=str(exc),
                    loc=Loc(type=LocType.LINE.value, value=0),
                )],
            )

        # ---- 检查 UTF-8（BOO-63 要求）----
        if encoding and encoding.lower() not in ("utf-8", "utf8", "ascii"):
            warnings.append(Warning(
                code="NON_UTF8_ENCODING",
                message=f"File encoding detected as '{encoding}', expected UTF-8.",
                loc=Loc(type=LocType.LINE.value, value=1),
            ))

        lines = text.split("\n")

        # ---- 提取 YAML front-matter ----
        metadata, fm_end_line = self._extract_frontmatter(lines)

        # ---- 去噪 ----
        cleaned_lines, noise_warnings = self._remove_noise(lines, fm_end_line)
        warnings.extend(noise_warnings)

        # ---- 按标题切分 sections ----
        sections = self._split_sections(cleaned_lines, fm_end_line)

        # ---- 提取 Markdown 表格 ----
        tables = self._extract_tables(cleaned_lines, fm_end_line, warnings)

        # ---- 检测图片引用 ----
        images = self._detect_images(cleaned_lines, fm_end_line, warnings)

        # ---- 标题 ----
        title = metadata.get("title", "")
        if not title:
            title = self._detect_title(sections, fpath)

        # ---- 质量检查 ----
        self._quality_check(cleaned_lines, sections, warnings)

        return ParsedDocument(
            doc_id=doc_id,
            source=self._source_dict(fpath),
            title=title,
            content_type="markdown",
            sections=sections,
            tables=tables,
            images=images,
            warnings=warnings,
            errors=errors,
            metadata={
                "frontmatter": metadata,
                "total_lines": len(lines),
                "encoding_detected": encoding,
                "total_sections": len(sections),
                "total_tables": len(tables),
            },
        )

    # ==================================================================
    # YAML Front-matter
    # ==================================================================
    def _extract_frontmatter(self, lines: list[str]) -> tuple[dict, int]:
        """提取 YAML front-matter，返回 (metadata_dict, end_line_index)"""
        if not lines or lines[0].strip() != "---":
            return {}, 0

        end_idx = -1
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                end_idx = i
                break

        if end_idx < 0:
            return {}, 0

        # 简易 YAML 解析（不引入 pyyaml 依赖）
        metadata: dict = {}
        for line in lines[1:end_idx]:
            m = re.match(r'^(\w[\w\s]*?):\s*(.*)$', line)
            if m:
                key = m.group(1).strip()
                val = m.group(2).strip()
                # 简单处理数组 [a, b, c]
                if val.startswith("[") and val.endswith("]"):
                    val = [v.strip().strip('"').strip("'") for v in val[1:-1].split(",")]
                # 去掉引号
                elif val.startswith('"') and val.endswith('"'):
                    val = val[1:-1]
                elif val.startswith("'") and val.endswith("'"):
                    val = val[1:-1]
                metadata[key] = val

        return metadata, end_idx + 1

    # ==================================================================
    # 去噪
    # ==================================================================
    def _remove_noise(
        self, lines: list[str], start_from: int
    ) -> tuple[list[str], list[Warning]]:
        """去掉页眉页脚、打印说明等噪声"""
        warnings: list[Warning] = []
        noise_patterns = [
            (r'第\s*\d+\s*页\s*/?\s*共\s*\d+\s*页', "PAGE_NUMBER"),
            (r'打印日期[：:].+', "PRINT_DATE"),
            (r'<!-- PAGE \d+ -->', "PAGE_MARKER"),
        ]

        cleaned = []
        noise_count = 0
        for li, line in enumerate(lines):
            if li < start_from:
                cleaned.append(line)
                continue
            is_noise = False
            for pattern, code in noise_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    is_noise = True
                    noise_count += 1
                    break
            if not is_noise:
                cleaned.append(line)
            else:
                cleaned.append("")  # 保持行号一致

        if noise_count > 0:
            warnings.append(Warning(
                code="NOISE_LINES_REMOVED",
                message=f"Removed {noise_count} noise line(s) (page numbers, print dates, etc.).",
                loc=Loc(type=LocType.LINE.value, value=0),
            ))

        return cleaned, warnings

    # ==================================================================
    # 按标题切分 Sections
    # ==================================================================
    def _split_sections(self, lines: list[str], start_from: int) -> list[Section]:
        sections: list[Section] = []
        current_heading = ""
        current_level = 1
        current_lines: list[str] = []
        current_start_line = start_from

        for li in range(start_from, len(lines)):
            line = lines[li]
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', line)

            if heading_match:
                # 保存上一段
                if current_heading or any(l.strip() for l in current_lines):
                    sections.append(Section(
                        heading=current_heading,
                        level=current_level,
                        content="\n".join(current_lines).strip(),
                        loc=Loc(type=LocType.LINE.value, value=current_start_line + 1),
                    ))
                current_heading = heading_match.group(2).strip()
                current_level = len(heading_match.group(1))
                current_lines = []
                current_start_line = li
            else:
                current_lines.append(line)

        # 最后一段
        if current_heading or any(l.strip() for l in current_lines):
            sections.append(Section(
                heading=current_heading,
                level=current_level,
                content="\n".join(current_lines).strip(),
                loc=Loc(type=LocType.LINE.value, value=current_start_line + 1),
            ))

        return sections

    # ==================================================================
    # 提取 Markdown 表格
    # ==================================================================
    def _extract_tables(
        self, lines: list[str], start_from: int,
        warnings: list[Warning],
    ) -> list[TableBlock]:
        """检测 Markdown 管道表格（| col1 | col2 |）"""
        tables: list[TableBlock] = []
        table_idx = 0
        i = start_from

        while i < len(lines):
            # 检测表格起始（至少两行管道行，第二行是分隔行）
            if self._is_table_row(lines[i]):
                table_start = i
                table_lines = [lines[i]]
                i += 1

                # 收集连续的管道行
                while i < len(lines) and self._is_table_row(lines[i]):
                    table_lines.append(lines[i])
                    i += 1

                # 至少需要 2 行（表头 + 分隔行），最好 3 行
                if len(table_lines) >= 2:
                    table_idx += 1
                    try:
                        tb = self._parse_md_table(
                            table_lines, table_start, table_idx, warnings
                        )
                        if tb:
                            tables.append(tb)
                    except Exception as exc:
                        warnings.append(Warning(
                            code="MD_TABLE_PARSE_ERROR",
                            message=f"Table at line {table_start+1}: {exc}",
                            loc=Loc(type=LocType.LINE.value, value=table_start + 1),
                        ))
            else:
                i += 1

        return tables

    @staticmethod
    def _is_table_row(line: str) -> bool:
        stripped = line.strip()
        return bool(stripped) and "|" in stripped

    def _parse_md_table(
        self, table_lines: list[str], start_line: int,
        table_idx: int, warnings: list[Warning],
    ) -> Optional[TableBlock]:
        """解析 Markdown 表格行"""

        # 解析每行的单元格
        def parse_row(line: str) -> list[str]:
            line = line.strip()
            if line.startswith("|"):
                line = line[1:]
            if line.endswith("|"):
                line = line[:-1]
            return [cell.strip() for cell in line.split("|")]

        if len(table_lines) < 2:
            return None

        # 第一行：表头
        headers = parse_row(table_lines[0])

        # 检测分隔行（---）
        sep_line_idx = 1
        sep_row = parse_row(table_lines[1])
        is_separator = all(
            re.match(r'^[-:]+$', cell.strip()) or cell.strip() == ""
            for cell in sep_row
        )

        data_start = 2 if is_separator else 1

        # 如果没有分隔行，第一行可能不是表头
        if not is_separator:
            warnings.append(Warning(
                code="MD_TABLE_NO_SEPARATOR",
                message=f"Table at line {start_line+1}: no separator row detected.",
                loc=Loc(type=LocType.LINE.value, value=start_line + 1),
            ))

        # 数据行
        rows = []
        for li in range(data_start, len(table_lines)):
            row = parse_row(table_lines[li])
            # 分隔行跳过
            if all(re.match(r'^[-:]+$', c.strip()) or c.strip() == "" for c in row):
                continue
            # 对齐列数
            while len(row) < len(headers):
                row.append("")
            rows.append(row[:len(headers)])

        if not rows and not headers:
            return None

        table_id = f"md_t{table_idx}"

        # 坐标映射
        coord_map = {}
        for ri in range(len(rows)):
            for ci in range(len(headers)):
                actual_line = start_line + data_start + ri + 1  # 1-based
                coord_map[f"{ri},{ci}"] = f"line{actual_line}"

        return TableBlock(
            meta=TableMeta(
                table_id=table_id,
                source_sheet="",
                source_range=f"lines {start_line+1}-{start_line+len(table_lines)}",
                row_count=len(rows),
                col_count=len(headers),
                coord_map=coord_map,
            ),
            headers=headers,
            rows=rows,
        )

    # ==================================================================
    # 图片检测
    # ==================================================================
    def _detect_images(
        self, lines: list[str], start_from: int,
        warnings: list[Warning],
    ) -> list[ImageBlock]:
        images: list[ImageBlock] = []
        img_pattern = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')

        for li in range(start_from, len(lines)):
            for m in img_pattern.finditer(lines[li]):
                alt_text = m.group(1)
                img_path = m.group(2)
                img_id = f"line{li+1}_img{len(images)+1}"

                images.append(ImageBlock(
                    image_id=img_id,
                    caption=alt_text,
                    path=img_path,
                    loc=Loc(type=LocType.LINE.value, value=li + 1),
                ))

                # 如果是本地图片（非 URL），提示可能需要 OCR
                if not img_path.startswith(("http://", "https://")):
                    warnings.append(Warning(
                        code="LOCAL_IMAGE_REFERENCE",
                        message=(
                            f"Line {li+1}: local image '{img_path}' referenced. "
                            "Text in images is not extracted. Consider OCR."
                        ),
                        loc=Loc(type=LocType.LINE.value, value=li + 1),
                    ))

        return images

    # ==================================================================
    # 质量检查
    # ==================================================================
    def _quality_check(
        self, lines: list[str], sections: list[Section],
        warnings: list[Warning],
    ):
        """BOO-63 内容质量检查"""
        # 1. 空文件
        text_content = "\n".join(lines).strip()
        if len(text_content) < 20:
            warnings.append(Warning(
                code="VERY_SHORT_CONTENT",
                message=f"File has very little content ({len(text_content)} chars).",
                loc=Loc(type=LocType.LINE.value, value=1),
            ))

        # 2. 没有标题结构
        if not any(s.heading for s in sections):
            warnings.append(Warning(
                code="NO_HEADINGS",
                message="No Markdown headings (# / ## / ###) detected; document structure is flat.",
                loc=Loc(type=LocType.LINE.value, value=1),
            ))

        # 3. 连续空行过多
        consecutive_empty = 0
        max_consecutive = 0
        for line in lines:
            if line.strip() == "":
                consecutive_empty += 1
                max_consecutive = max(max_consecutive, consecutive_empty)
            else:
                consecutive_empty = 0
        if max_consecutive > 5:
            warnings.append(Warning(
                code="EXCESSIVE_BLANK_LINES",
                message=f"Found {max_consecutive} consecutive blank lines.",
                loc=Loc(type=LocType.LINE.value, value=0),
            ))

    # ==================================================================
    # 辅助
    # ==================================================================
    def _detect_title(self, sections: list[Section], fpath: Path) -> str:
        for s in sections:
            if s.heading and s.level == 1:
                return s.heading
        for s in sections:
            if s.heading:
                return s.heading
        return fpath.stem

    def _source_dict(self, fpath: Path) -> dict:
        return {
            "file_name": fpath.name,
            "file_type": fpath.suffix.lstrip("."),
            "file_size_bytes": fpath.stat().st_size,
            "file_path": str(fpath),
        }