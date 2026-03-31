"""
agent/parser/main.py

批量解析入口。
默认路径：
    源文件:  D:/finance/finance-agent/docs/raw
    输出:    D:/finance/finance-agent/docs/parsed
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from agent.parser.router import FileRouter
from agent.parser.output.writer import ParsedOutputWriter
from agent.parser.output.manifest import generate_manifest

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 默认路径
# ---------------------------------------------------------------------------
DEFAULT_RAW_DIR = Path(r"D:\\finance\\finance-agent\\docs\\raw")
DEFAULT_PARSED_DIR = Path(r"D:\\finance\\finance-agent\\docs\\parsed")

# 支持的文件后缀
SUPPORTED_EXTENSIONS = {
    ".pdf", ".docx", ".pptx", ".xlsx", ".xls",
    ".md", ".markdown", ".txt",
}


def parse_single_file(
    file_path: str,
    parsed_output_dir: str | Path,
    kb_name: str = "",
) -> dict[str, Any]:
    """
    解析单个文件 → 写出 parsed/ 产物 → 返回结果摘要。
    """
    router = FileRouter(kb_name=kb_name)
    doc = router.parse_file(file_path)

    writer = ParsedOutputWriter(parsed_output_dir)
    doc_dir = writer.write(doc)

    # 表格索引
    tables_info = []
    for tb in doc.tables:
        tables_info.append({
            "csv": str(doc_dir / "tables" / f"{tb.meta.table_id}.csv"),
            "format": str(doc_dir / "tables" / f"{tb.meta.table_id}.format.json"),
        })

    return {
        "file_path": file_path,
        "doc_id": doc.doc_id,
        "status": doc.status,
        "parsed_dir": str(doc_dir),
        "tables": tables_info,
        "title": doc.title,
        "warnings_count": len(doc.warnings),
        "errors_count": len(doc.errors),
    }


def parse_directory(
    raw_dir: str | Path = DEFAULT_RAW_DIR,
    parsed_dir: str | Path = DEFAULT_PARSED_DIR,
    kb_name: str = "finance",
    owner: str = "",
    source_summary: str = "",
) -> dict[str, Any]:
    """
    扫描 raw_dir 下所有受支持的文件，逐个解析，输出到 parsed_dir。

    默认：
        raw_dir:    D:/finance/finance-agent/docs/raw
        parsed_dir: D:/finance/finance-agent/docs/parsed
    """
    raw_dir = Path(raw_dir)
    parsed_dir = Path(parsed_dir)

    # 确保输出目录存在
    parsed_dir.mkdir(parents=True, exist_ok=True)

    # 收集要处理的文件（递归扫描）
    files_to_parse: list[Path] = []
    if raw_dir.exists():
        for f in raw_dir.rglob("*"):
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS:
                files_to_parse.append(f)
    else:
        logger.error(f"Raw directory not found: {raw_dir}")
        return {"error": f"Directory not found: {raw_dir}", "total": 0}

    logger.info(f"Found {len(files_to_parse)} files in {raw_dir}")
    if not files_to_parse:
        logger.warning("No supported files found!")

    # 按文件名排序，确保稳定顺序
    files_to_parse.sort(key=lambda f: f.name)

    # 逐个解析
    results: list[dict] = []
    for i, fpath in enumerate(files_to_parse, 1):
        logger.info(f"[{i}/{len(files_to_parse)}] Parsing: {fpath.name}")
        try:
            result = parse_single_file(
                str(fpath),
                str(parsed_dir),
                kb_name=kb_name,
            )
            results.append(result)
            status_emoji = {
                "success": "✅",
                "partial": "⚠️",
                "error": "❌",
            }.get(result["status"], "❓")
            logger.info(
                f"  {status_emoji} {result['status']} | "
                f"doc_id={result['doc_id']} | "
                f"warnings={result['warnings_count']} "
                f"errors={result['errors_count']}"
            )
        except Exception as exc:
            results.append({
                "file_path": str(fpath),
                "doc_id": "",
                "status": "error",
                "error": str(exc),
            })
            logger.error(f"  ❌ FAILED: {exc}")

    # 生成 manifest.json（放在 parsed_dir 下）
    manifest_path = generate_manifest(
        kb_name=kb_name,
        kb_dir=parsed_dir,
        parsed_results=results,
        owner=owner,
        source_summary=source_summary,
    )

    # 汇总
    status_counts = {"success": 0, "partial": 0, "error": 0}
    for r in results:
        s = r.get("status", "error")
        if s in status_counts:
            status_counts[s] += 1

    summary = {
        "kb_name": kb_name,
        "raw_dir": str(raw_dir),
        "parsed_dir": str(parsed_dir),
        "total": len(results),
        **status_counts,
        "results": results,
        "manifest_path": str(manifest_path),
    }

    # 打印汇总
    logger.info(
        f"\n{'='*60}\n"
        f"  Parse Complete: {kb_name}\n"
        f"  Raw:     {raw_dir}\n"
        f"  Parsed:  {parsed_dir}\n"
        f"  Total:   {summary['total']}\n"
        f"  Success: {summary['success']}\n"
        f"  Partial: {summary['partial']}\n"
        f"  Error:   {summary['error']}\n"
        f"  Manifest: {manifest_path}\n"
        f"{'='*60}"
    )

    return summary


# 保留 parse_knowledge_base 兼容旧接口
def parse_knowledge_base(
    kb_name: str,
    kb_dir: str | Path,
    owner: str = "",
    source_summary: str = "",
) -> dict[str, Any]:
    """
    兼容旧接口：按 BOO-63 标准目录结构解析。
    预期 kb_dir 下有 raw/ 子目录，输出到 kb_dir/normalized/parsed/。
    """
    kb_dir = Path(kb_dir)
    raw_dir = kb_dir / "raw"
    parsed_dir = kb_dir / "normalized" / "parsed"
    parsed_dir.mkdir(parents=True, exist_ok=True)

    return parse_directory(
        raw_dir=raw_dir,
        parsed_dir=parsed_dir,
        kb_name=kb_name,
        owner=owner,
        source_summary=source_summary,
    )


# ------------------------------------------------------------------
# CLI 入口
# ------------------------------------------------------------------
if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Parse documents for knowledge base",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # 使用默认路径
  python -m agent.parser.main

  # 指定路径
  python -m agent.parser.main --raw D:/finance/finance-agent/docs/raw --out D:/finance/finance-agent/docs/parsed

  # BOO-63 标准目录模式
  python -m agent.parser.main --mode kb --kb-name reimbursement --kb-dir docs/reimbursement
        """,
    )

    parser.add_argument(
        "--mode", choices=["dir", "kb"], default="dir",
        help="'dir': raw→parsed 直接模式; 'kb': BOO-63 标准知识库目录模式"
    )
    parser.add_argument(
        "--raw",
        default=str(DEFAULT_RAW_DIR),
        help=f"Source directory (default: {DEFAULT_RAW_DIR})"
    )
    parser.add_argument(
        "--out",
        default=str(DEFAULT_PARSED_DIR),
        help=f"Output directory (default: {DEFAULT_PARSED_DIR})"
    )
    parser.add_argument("--kb-name", default="finance", help="Knowledge base name")
    parser.add_argument("--kb-dir", default="", help="KB directory (for --mode kb)")
    parser.add_argument("--owner", default="", help="Owner name")
    parser.add_argument("--source", default="", help="Source summary")
    parser.add_argument(
        "--check-ocr", action="store_true",
        help="Check OCR API connectivity before parsing"
    )

    args = parser.parse_args()

    # OCR 连通性检查
    if args.check_ocr:
        from agent.parser.utils.ocr_utils import check_api_connectivity
        result = check_api_connectivity()
        if result["ok"]:
            logger.info(f"✅ OCR API: {result['message']}")
        else:
            logger.error(f"❌ OCR API: {result['message']}")
            exit(1)

    # 执行解析
    if args.mode == "kb" and args.kb_dir:
        result = parse_knowledge_base(
            kb_name=args.kb_name,
            kb_dir=args.kb_dir,
            owner=args.owner,
            source_summary=args.source,
        )
    else:
        result = parse_directory(
            raw_dir=args.raw,
            parsed_dir=args.out,
            kb_name=args.kb_name,
            owner=args.owner,
            source_summary=args.source,
        )

    # 输出 JSON 结果
    print(json.dumps(result, ensure_ascii=False, indent=2))