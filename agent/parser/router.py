"""
agent/parser/router.py
"""
from __future__ import annotations

from pathlib import Path

from agent.parser.base import BaseParser
from agent.parser.schema import ParsedDocument


class FileRouter:
    def __init__(self, kb_name: str = ""):
        from agent.parser.parsers.pdf_parser import PDFParser
        from agent.parser.parsers.docx_parser import DocxParser
        from agent.parser.parsers.pptx_parser import PptxParser
        from agent.parser.parsers.excel_parser import ExcelParser
        from agent.parser.parsers.markdown_parser import MarkdownParser

        self._parsers: list[BaseParser] = [
            PDFParser(kb_name=kb_name),
            DocxParser(kb_name=kb_name),
            PptxParser(kb_name=kb_name),
            ExcelParser(kb_name=kb_name),
            MarkdownParser(kb_name=kb_name),
        ]

    def route(self, file_path: str) -> BaseParser:
        for parser in self._parsers:
            if parser.can_handle(file_path):
                return parser
        raise ValueError(
            f"No parser for extension: {Path(file_path).suffix}. "
            f"Supported: {self.supported_extensions}"
        )

    def parse_file(self, file_path: str, **kwargs) -> ParsedDocument:
        parser = self.route(file_path)
        return parser.safe_parse(file_path, **kwargs)

    @property
    def supported_extensions(self) -> list[str]:
        exts = []
        for p in self._parsers:
            exts.extend(p.supported_extensions)
        return exts