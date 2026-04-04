from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from agent.tools.base import ToolResult, ok


def _db_path(path: str | None = None) -> Path:
    target = Path(path or "data/db/reimburse.db").resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS reimburse_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            payload_json TEXT NOT NULL
        )
        """
    )
    conn.commit()


def save_record(record: Dict[str, Any], db_path: str | None = None) -> ToolResult:
    target = _db_path(db_path)
    payload_json = json.dumps(record, ensure_ascii=False)
    try:
        conn = sqlite3.connect(target)
        _ensure_schema(conn)
        cursor = conn.execute(
            "INSERT INTO reimburse_records (created_at, payload_json) VALUES (?, ?)",
            (datetime.now().isoformat(timespec="seconds"), payload_json),
        )
        conn.commit()
        rec_id = int(cursor.lastrowid)
        conn.close()
        return ok(saved=True, record_id=rec_id, db_path=str(target))
    except Exception:
        fallback = Path("data/db/reimburse_records_backup.json").resolve()
        fallback.parent.mkdir(parents=True, exist_ok=True)
        existing: List[Dict[str, Any]] = []
        if fallback.exists():
            existing = json.loads(fallback.read_text(encoding="utf-8"))
        existing.append({"created_at": datetime.now().isoformat(timespec="seconds"), "record": record})
        fallback.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
        return ok(saved=False, fallback_used=True, backup_path=str(fallback))


def load_records(filters: Dict[str, Any] | None = None, db_path: str | None = None) -> ToolResult:
    target = _db_path(db_path)
    filters = filters or {}
    try:
        conn = sqlite3.connect(target)
        _ensure_schema(conn)
        rows = conn.execute("SELECT id, created_at, payload_json FROM reimburse_records ORDER BY id DESC").fetchall()
        conn.close()
        records: List[Dict[str, Any]] = []
        for rec_id, created_at, payload_json in rows:
            payload = json.loads(payload_json)
            payload["id"] = rec_id
            payload["created_at"] = created_at
            records.append(payload)
        return ok(records=records)
    except Exception:
        fallback = Path("data/db/reimburse_records_backup.json").resolve()
        if not fallback.exists():
            return ok(records=[])
        payload = json.loads(fallback.read_text(encoding="utf-8"))
        records = [item.get("record", {}) for item in payload]
        return ok(records=records, fallback_used=True)
