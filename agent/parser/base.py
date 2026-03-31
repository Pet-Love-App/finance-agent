"""
agent/parser/base.py

所有解析器的基类。
核心契约：file_path -> ParsedDocument + text.md + tables/
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from pathlib import Path

from agent.parser.schema import (
    Error, Loc, LocType, ParseStatus, ParsedDocument, Warning,
)


class BaseParser(ABC):
    """
    解析器基类。
    子类只需实现 parse()，base 提供 safe_parse() 做统一错误兜底。
    """

    supported_extensions: list[str] = []

    # ------------------------------------------------------------------
    # 子类必须实现
    # ------------------------------------------------------------------
    @abstractmethod
    def parse(self, file_path: str, **kwargs) -> ParsedDocument:
        """
        解析单个文件，返回 ParsedDocument。
        - 遇到不确定/降级/猜测 → 写入 warnings（带 loc）
        - 遇到致命问题 → 写入 errors（带 error_code + loc）
        - 禁止静默吞错
        """
        ...

    # ------------------------------------------------------------------
    # 通用入口（带兜底）
    # ------------------------------------------------------------------
    def safe_parse(self, file_path: str, **kwargs) -> ParsedDocument:
        start = time.time()
        try:
            doc = self.parse(file_path, **kwargs)
            doc.metadata["parse_duration_sec"] = round(time.time() - start, 3)
            doc.metadata["parser_class"] = self.__class__.__name__

            # 根据 warnings/errors 修正 status
            if doc.errors:
                doc.status = ParseStatus.ERROR.value
            elif doc.warnings:
                doc.status = ParseStatus.PARTIAL.value
            else:
                doc.status = ParseStatus.SUCCESS.value

            return doc

        except Exception as exc:
            duration = round(time.time() - start, 3)
            return ParsedDocument(
                doc_id="",
                status=ParseStatus.ERROR.value,
                source={
                    "file_name": Path(file_path).name,
                    "file_type": Path(file_path).suffix.lstrip("."),
                    "file_path": file_path,
                },
                errors=[Error(
                    error_code="UNHANDLED_EXCEPTION",
                    message=f"{type(exc).__name__}: {exc}",
                    loc=Loc(type=LocType.LINE.value, value=0),
                )],
                metadata={
                    "parse_duration_sec": duration,
                    "parser_class": self.__class__.__name__,
                },
            )

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------
    def can_handle(self, file_path: str) -> bool:
        return Path(file_path).suffix.lower() in self.supported_extensions