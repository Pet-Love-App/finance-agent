"""
agent/parser/output/writer.py

将 ParsedDocument 写出为 BOO-63 规范的目录结构：
  normalized/parsed/<doc_id>/
    document.json
    text.md
    tables/
      t1.csv
      t1.format.json
"""
from __future__ import annotations

import csv
import json
import logging
from pathlib import Path

from agent.parser.schema import ParsedDocument, TableBlock
from agent.parser.postprocess.text_md_renderer import TextMdRenderer

logger = logging.getLogger(__name__)


class ParsedOutputWriter:
    """写出单个文档的 parsed/ 产物"""

    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir)

    def write(self, doc: ParsedDocument) -> Path:
        """
        写出完整产物，返回 doc_dir 路径。
        """
        doc_dir = self.base_dir / doc.doc_id
        doc_dir.mkdir(parents=True, exist_ok=True)

        # 1. document.json
        self._write_document_json(doc, doc_dir)

        # 2. text.md
        self._write_text_md(doc, doc_dir)

        # 3. tables/
        if doc.tables:
            self._write_tables(doc.tables, doc_dir)

        logger.info(f"Written parsed output: {doc_dir}")
        return doc_dir

    def _write_document_json(self, doc: ParsedDocument, doc_dir: Path):
        out_path = doc_dir / "document.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(doc.to_dict(), f, ensure_ascii=False, indent=2, default=str)

    def _write_text_md(self, doc: ParsedDocument, doc_dir: Path):
        renderer = TextMdRenderer()
        text_md = renderer.render(doc)
        out_path = doc_dir / "text.md"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(text_md)

    def _write_tables(self, tables: list[TableBlock], doc_dir: Path):
        tables_dir = doc_dir / "tables"
        tables_dir.mkdir(exist_ok=True)

        for tb in tables:
            table_id = tb.meta.table_id

            # CSV
            csv_path = tables_dir / f"{table_id}.csv"
            with open(csv_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(tb.headers)
                for row in tb.rows:
                    writer.writerow([
                        str(v) if v is not None else "" for v in row
                    ])

            # format.json
            fmt_path = tables_dir / f"{table_id}.format.json"
            fmt_data = tb.meta.to_dict()
            with open(fmt_path, "w", encoding="utf-8") as f:
                json.dump(fmt_data, f, ensure_ascii=False, indent=2, default=str)