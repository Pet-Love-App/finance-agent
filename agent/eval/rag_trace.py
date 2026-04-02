from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def _utc_timestamp() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


@dataclass(frozen=True)
class RAGTraceContext:
    source: str
    title: str
    content: str
    score: float


@dataclass(frozen=True)
class RAGTraceRecord:
    request_id: str
    timestamp: str
    status: str
    question: str
    contexts: List[RAGTraceContext]
    answer: str
    latency_ms: int
    mode: str = "rag"
    error: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        if payload.get("meta") is None:
            payload["meta"] = {}
        return payload


def _normalize_contexts(contexts: Iterable[Any]) -> List[RAGTraceContext]:
    normalized: List[RAGTraceContext] = []

    for item in contexts:
        if isinstance(item, dict):
            source = str(item.get("source", "")).strip() or "unknown"
            title = str(item.get("title", "")).strip() or "untitled"
            content = str(item.get("content", "")).strip()
            score = _safe_float(item.get("score", 0.0))
        else:
            source = str(getattr(item, "source", "")).strip() or "unknown"
            title = str(getattr(item, "title", "")).strip() or "untitled"
            content = str(getattr(item, "content", "")).strip()
            score = _safe_float(getattr(item, "score", 0.0))

        normalized.append(
            RAGTraceContext(
                source=source,
                title=title,
                content=content,
                score=score,
            )
        )

    return normalized


def build_trace_record(
    *,
    request_id: str,
    status: str,
    question: str,
    contexts: Iterable[Any],
    answer: str,
    latency_ms: int,
    mode: str = "rag",
    error: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> RAGTraceRecord:
    normalized_status = status if status in {"ok", "error"} else "ok"
    safe_meta = dict(meta or {})

    return RAGTraceRecord(
        request_id=request_id.strip() or "unknown",
        timestamp=_utc_timestamp(),
        status=normalized_status,
        question=question.strip(),
        contexts=_normalize_contexts(contexts),
        answer=answer.strip(),
        latency_ms=max(int(latency_ms), 0),
        mode=mode.strip() or "rag",
        error=(error or None),
        meta=safe_meta,
    )


class RAGTraceStore:
    def __init__(self, base_dir: str | Path) -> None:
        self.base_dir = Path(base_dir)

    def _target_path(self, dt: Optional[datetime] = None) -> Path:
        current = dt or datetime.now(tz=timezone.utc)
        file_name = f"rag_trace_{current.strftime('%Y%m%d')}.jsonl"
        return self.base_dir / file_name

    def append(self, record: RAGTraceRecord) -> Path:
        target = self._target_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
        return target
