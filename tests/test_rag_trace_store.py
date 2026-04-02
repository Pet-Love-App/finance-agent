from __future__ import annotations

import json
from pathlib import Path

from agent.eval import RAGTraceStore, build_trace_record


def test_rag_trace_store_append_ok_record(tmp_path: Path) -> None:
    store = RAGTraceStore(base_dir=tmp_path)
    record = build_trace_record(
        request_id="req-1",
        status="ok",
        question="高铁报销标准是什么？",
        contexts=[
            {
                "source": "kb.md",
                "title": "差旅制度",
                "content": "高铁二等座可报销。",
                "score": 0.91,
            }
        ],
        answer="一般按制度报销高铁二等座。",
        latency_ms=128,
        mode="llm_sync",
    )

    path = store.append(record)

    assert path.exists()
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1

    payload = json.loads(lines[0])
    assert payload["request_id"] == "req-1"
    assert payload["status"] == "ok"
    assert payload["question"]
    assert isinstance(payload["contexts"], list)
    assert payload["latency_ms"] == 128


def test_rag_trace_store_append_error_record(tmp_path: Path) -> None:
    store = RAGTraceStore(base_dir=tmp_path)
    record = build_trace_record(
        request_id="req-err",
        status="error",
        question="规则？",
        contexts=[],
        answer="",
        latency_ms=23,
        mode="llm_stream",
        error="timeout",
        meta={"stream": True},
    )

    path = store.append(record)
    payload = json.loads(path.read_text(encoding="utf-8").strip())

    assert payload["status"] == "error"
    assert payload["error"] == "timeout"
    assert payload["meta"]["stream"] is True
