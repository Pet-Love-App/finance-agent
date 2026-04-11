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
            session_id TEXT DEFAULT '',
            payload_json TEXT NOT NULL
        )
        """
    )
    columns = [row[1] for row in conn.execute("PRAGMA table_info(reimburse_records)").fetchall()]
    if "session_id" not in columns:
        conn.execute("ALTER TABLE reimburse_records ADD COLUMN session_id TEXT DEFAULT ''")
    conn.commit()


def save_record(record: Dict[str, Any], db_path: str | None = None, session_id: str | None = None) -> ToolResult:
    target = _db_path(db_path)
    payload_json = json.dumps(record, ensure_ascii=False)
    session = str(session_id or "").strip()
    try:
        conn = sqlite3.connect(target)
        _ensure_schema(conn)
        cursor = conn.execute(
            "INSERT INTO reimburse_records (created_at, session_id, payload_json) VALUES (?, ?, ?)",
            (datetime.now().isoformat(timespec="seconds"), session, payload_json),
        )
        conn.commit()
        rec_id = int(cursor.lastrowid)
        conn.close()
        return ok(saved=True, record_id=rec_id, db_path=str(target), session_id=session)
    except Exception:
        fallback = Path("data/db/reimburse_records_backup.json").resolve()
        fallback.parent.mkdir(parents=True, exist_ok=True)
        existing: List[Dict[str, Any]] = []
        if fallback.exists():
            existing = json.loads(fallback.read_text(encoding="utf-8"))
        existing.append({"created_at": datetime.now().isoformat(timespec="seconds"), "session_id": session, "record": record})
        fallback.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
        return ok(saved=False, fallback_used=True, backup_path=str(fallback), session_id=session)


def load_records(filters: Dict[str, Any] | None = None, db_path: str | None = None) -> ToolResult:
    target = _db_path(db_path)
    filters = filters or {}
    session_id = str(filters.get("session_id", filters.get("chat_session_id", "")) or "").strip()
    try:
        conn = sqlite3.connect(target)
        _ensure_schema(conn)
        if session_id:
            rows = conn.execute(
                "SELECT id, created_at, session_id, payload_json FROM reimburse_records WHERE session_id = ? ORDER BY id DESC",
                (session_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, created_at, session_id, payload_json FROM reimburse_records ORDER BY id DESC"
            ).fetchall()
        conn.close()
        records: List[Dict[str, Any]] = []
        for rec_id, created_at, row_session_id, payload_json in rows:
            payload = json.loads(payload_json)
            payload["id"] = rec_id
            payload["created_at"] = created_at
            payload["session_id"] = row_session_id or ""
            records.append(payload)
        return ok(records=records)
    except Exception:
        fallback = Path("data/db/reimburse_records_backup.json").resolve()
        if not fallback.exists():
            return ok(records=[])
        payload = json.loads(fallback.read_text(encoding="utf-8"))
        records = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            row_session_id = str(item.get("session_id", "") or "").strip()
            if session_id and row_session_id != session_id:
                continue
            record = item.get("record", {})
            if isinstance(record, dict):
                record.setdefault("session_id", row_session_id)
            records.append(record)
        return ok(records=records, fallback_used=True)
