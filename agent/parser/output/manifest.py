"""
agent/parser/output/manifest.py

生成 docs/<kb_name>/manifest.json。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def generate_manifest(
    kb_name: str,
    kb_dir: str | Path,
    parsed_results: list[dict],   # 每个元素是 parse_single_file 的返回
    owner: str = "",
    source_summary: str = "",
) -> Path:
    """
    生成 manifest.json 并写入 kb_dir。

    parsed_results 元素格式:
    {
        "file_path": "raw/xxx.xlsx",
        "doc_id": "reimbursement__xxx__sha1xxxx",
        "status": "success" | "partial" | "error",
        "parsed_dir": "normalized/parsed/<doc_id>/",
        "tables": [{"csv": "...", "format": "..."}],
        "error": "..."  (仅 error 时)
    }
    """
    kb_dir = Path(kb_dir)
    manifest = {
        "kb_name": kb_name,
        "deliver_version": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "owner": owner,
        "source_summary": source_summary,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "files": [],
    }

    for result in parsed_results:
        entry: dict[str, Any] = {
            "path": result.get("file_path", ""),
            "type": Path(result.get("file_path", "")).suffix.lstrip("."),
            "status": result.get("status", "unknown"),
        }

        if result.get("doc_id"):
            parsed_base = f"normalized/parsed/{result['doc_id']}"
            entry["parsed"] = {
                "document_json": f"{parsed_base}/document.json",
                "text_md": f"{parsed_base}/text.md",
            }
            if result.get("tables"):
                entry["parsed"]["tables"] = result["tables"]

        if result.get("error"):
            entry["error"] = result["error"]

        manifest["files"].append(entry)

    out_path = kb_dir / "manifest.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    return out_path