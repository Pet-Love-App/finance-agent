from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict


class AuditLogger:
    def __init__(self, log_path: str | None = None, retention_days: int = 180) -> None:
        default_path = Path("data") / "audit" / "sandbox_audit.jsonl"
        self.log_path = Path(log_path) if log_path else default_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.retention_days = retention_days

    def append(self, record: Dict[str, Any]) -> str:
        now = datetime.now(timezone.utc).isoformat()
        payload = {"logged_at": now, **record}
        with self.log_path.open("a", encoding="utf-8") as writer:
            writer.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return str(self.log_path.resolve())

    def prune(self) -> int:
        if not self.log_path.exists():
            return 0

        cutoff = datetime.now(timezone.utc) - timedelta(days=self.retention_days)
        kept = []
        removed = 0

        with self.log_path.open("r", encoding="utf-8") as reader:
            for line in reader:
                text = line.strip()
                if not text:
                    continue
                try:
                    item = json.loads(text)
                    timestamp = datetime.fromisoformat(item.get("logged_at"))
                    if timestamp >= cutoff:
                        kept.append(text)
                    else:
                        removed += 1
                except Exception:
                    kept.append(text)

        with self.log_path.open("w", encoding="utf-8") as writer:
            for line in kept:
                writer.write(line + "\n")
        return removed
