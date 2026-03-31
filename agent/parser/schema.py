"""
agent/parser/schema.py

BOO-63 对齐的数据模型。
核心设计：document.json 的完整结构定义，含 warnings/errors + loc 坐标映射。
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Optional


# ---------------------------------------------------------------------------
# 枚举
# ---------------------------------------------------------------------------
class ParseStatus(str, enum.Enum):
    SUCCESS = "success"
    PARTIAL = "partial"          # 有 warnings 但主流程完成
    ERROR = "error"              # 解析失败


class LocType(str, enum.Enum):
    """坐标定位类型，用于前端跳转"""
    PAGE = "page"                # PDF 页码
    PARAGRAPH = "paragraph"      # Word 段落序号
    SLIDE = "slide"              # PPT 幻灯片序号
    CELL = "cell"                # Excel 单元格 A1
    RANGE = "range"              # Excel 区域 A1:H40
    SHEET = "sheet"              # Excel Sheet 名
    LINE = "line"                # 通用行号


# ---------------------------------------------------------------------------
# 坐标 / 告警 / 错误
# ---------------------------------------------------------------------------
@dataclass
class Loc:
    """可定位坐标 —— 映射回原文档"""
    type: str                    # LocType 值
    value: str | int             # "A1" / 3 / "Sheet-标准"
    extra: dict = field(default_factory=dict)   # 如 {"sheet": "标准", "slide": 2}

    def to_dict(self) -> dict:
        d = {"type": self.type, "value": self.value}
        if self.extra:
            d["extra"] = self.extra
        return d


@dataclass
class Warning:
    """解析过程中的非致命问题"""
    code: str                    # 如 "MERGED_CELL_EXPAND", "EMPTY_ROWS_SKIPPED"
    message: str
    loc: Optional[Loc] = None

    def to_dict(self) -> dict:
        d = {"code": self.code, "message": self.message}
        if self.loc:
            d["loc"] = self.loc.to_dict()
        return d


@dataclass
class Error:
    """解析过程中的致命问题"""
    error_code: str              # 如 "OCR_FAILED", "SHEET_READ_ERROR"
    message: str
    loc: Optional[Loc] = None

    def to_dict(self) -> dict:
        d = {"error_code": self.error_code, "message": self.message}
        if self.loc:
            d["loc"] = self.loc.to_dict()
        return d


# ---------------------------------------------------------------------------
# 表格
# ---------------------------------------------------------------------------
@dataclass
class TableMeta:
    """一个表块的元信息 —— 对应 tables/<table_id>.format.json"""
    table_id: str
    source_sheet: str = ""
    source_range: str = ""       # "A1:H40"
    header_rows: list[int] = field(default_factory=lambda: [1])
    merged_cells: list[str] = field(default_factory=list)   # ["A1:C1"]
    freeze_panes: str = ""
    units: dict[str, str] = field(default_factory=dict)
    number_formats: dict[str, str] = field(default_factory=dict)
    notes: str = ""
    row_count: int = 0
    col_count: int = 0
    # 坐标映射：csv (row_idx, col_idx) -> Excel A1
    coord_map: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v or isinstance(v, (int, float))}


@dataclass
class TableBlock:
    """解析出的一个表块"""
    meta: TableMeta
    headers: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)  # 二维数组，同 CSV 内容


# ---------------------------------------------------------------------------
# 文档段落 / Slide / Section
# ---------------------------------------------------------------------------
@dataclass
class Section:
    """文档结构段（Word/PDF 标题段）"""
    heading: str
    level: int                   # 1-6
    content: str                 # 该段纯文本
    loc: Optional[Loc] = None

    def to_dict(self) -> dict:
        d = {"heading": self.heading, "level": self.level, "content": self.content}
        if self.loc:
            d["loc"] = self.loc.to_dict()
        return d


@dataclass
class SlideContent:
    """PPT 单页内容"""
    slide_number: int
    title: str = ""
    bullets: list[str] = field(default_factory=list)
    notes: str = ""
    text_blocks: list[str] = field(default_factory=list)  # 非 bullet 的文本框
    tables: list[TableBlock] = field(default_factory=list)
    loc: Optional[Loc] = None

    def to_dict(self) -> dict:
        d = {
            "slide_number": self.slide_number,
            "title": self.title,
            "bullets": self.bullets,
            "notes": self.notes,
        }
        if self.text_blocks:
            d["text_blocks"] = self.text_blocks
        if self.loc:
            d["loc"] = self.loc.to_dict()
        return d


# ---------------------------------------------------------------------------
# 图片
# ---------------------------------------------------------------------------
@dataclass
class ImageBlock:
    image_id: str
    caption: str = ""
    path: str = ""               # 导出路径
    ocr_text: str = ""
    loc: Optional[Loc] = None

    def to_dict(self) -> dict:
        d = {"image_id": self.image_id, "caption": self.caption}
        if self.path:
            d["path"] = self.path
        if self.ocr_text:
            d["ocr_text"] = self.ocr_text
        if self.loc:
            d["loc"] = self.loc.to_dict()
        return d


# ---------------------------------------------------------------------------
# document.json 顶层结构
# ---------------------------------------------------------------------------
@dataclass
class ParsedDocument:
    """
    对应 normalized/parsed/<doc_id>/document.json
    BOO-63 核心交付数据对象。
    """
    doc_id: str
    status: str = ParseStatus.SUCCESS.value
    source: dict = field(default_factory=dict)   # file_name, file_type, ...
    title: str = ""
    content_type: str = ""       # "word" / "excel" / "pdf" / "pptx"

    # 结构化内容
    sections: list[Section] = field(default_factory=list)
    slides: list[SlideContent] = field(default_factory=list)    # PPT 专用
    tables: list[TableBlock] = field(default_factory=list)
    images: list[ImageBlock] = field(default_factory=list)

    # 质量与审计
    warnings: list[Warning] = field(default_factory=list)
    errors: list[Error] = field(default_factory=list)

    # 元数据
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "doc_id": self.doc_id,
            "status": self.status,
            "source": self.source,
            "title": self.title,
            "content_type": self.content_type,
            "sections": [s.to_dict() for s in self.sections],
            "slides": [s.to_dict() for s in self.slides],
            "tables": [
                {
                    "table_id": t.meta.table_id,
                    "headers": t.headers,
                    "row_count": t.meta.row_count,
                    "source_sheet": t.meta.source_sheet,
                    "source_range": t.meta.source_range,
                }
                for t in self.tables
            ],
            "images": [img.to_dict() for img in self.images],
            "warnings": [w.to_dict() for w in self.warnings],
            "errors": [e.to_dict() for e in self.errors],
            "metadata": self.metadata,
        }