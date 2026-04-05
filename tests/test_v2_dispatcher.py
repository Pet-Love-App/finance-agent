from __future__ import annotations

import unittest
from pathlib import Path
import sys
from types import ModuleType
from unittest.mock import patch

repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))


def _install_fake_pandas() -> None:
    class _FakeSeries:
        def __init__(self, values):
            self.values = values

        def sum(self):
            return float(sum(float(v or 0) for v in self.values))

    class _FakeGroupByColumn:
        def __init__(self, rows, key, col):
            self._rows = rows
            self._key = key
            self._col = col

        def sum(self):
            grouped = {}
            for row in self._rows:
                group_key = row.get(self._key, "unknown")
                grouped[group_key] = grouped.get(group_key, 0.0) + float(row.get(self._col, 0) or 0)
            return _FakeDataFrame([{self._key: k, self._col: v} for k, v in grouped.items()])

    class _FakeGroupBy:
        def __init__(self, rows, key):
            self._rows = rows
            self._key = key

        def __getitem__(self, col):
            return _FakeGroupByColumn(self._rows, self._key, col)

    class _FakeDataFrame:
        def __init__(self, rows=None):
            self._rows = list(rows or [])

        def groupby(self, key, as_index=False):
            return _FakeGroupBy(self._rows, key)

        def to_dict(self, orient="records"):
            if orient != "records":
                raise ValueError("Only records orient is supported in fake pandas")
            return [dict(row) for row in self._rows]

        def to_excel(self, path, index=False):
            Path(path).write_text("[]", encoding="utf-8")

    fake_pd = ModuleType("pandas")
    fake_pd.DataFrame = _FakeDataFrame
    sys.modules["pandas"] = fake_pd


_install_fake_pandas()

from agent import EventBus, TaskDispatcher


class TestV2Dispatcher(unittest.TestCase):
    def setUp(self) -> None:
        self.bus = EventBus()
        self.dispatcher = TaskDispatcher(self.bus)

    def test_qa_route(self) -> None:
        result = self.dispatcher.dispatch("qa", {"query": "餐饮发票能报销吗？"})
        self.assertEqual(result.get("type"), "qa")
        self.assertTrue(bool(result.get("answer")))

    def test_reimburse_route(self) -> None:
        source_file = str(Path("docs/parsed/text.md").resolve())
        result = self.dispatcher.dispatch(
            "reimburse",
            {
                "paths": [source_file],
                "activity_text": "2026-03-10 在教室举办活动",
                "rules": {"max_amount": 50000, "required_activity_date": True},
            },
        )
        self.assertEqual(result.get("type"), "reimburse")
        self.assertIn("record_id", result)

    def test_final_account_route(self) -> None:
        result = self.dispatcher.dispatch("final_account", {"filters": {}})
        self.assertEqual(result.get("type"), "final_account")
        self.assertIn("aggregate", result)

    def test_budget_route(self) -> None:
        result = self.dispatcher.dispatch(
            "budget",
            {
                "aggregate": {"total_amount": 1000.0, "count": 3, "by_month": []},
                "strategy": {"growth_rate": 0.1},
            },
        )
        self.assertEqual(result.get("type"), "budget")
        self.assertIn("budget", result)

    def test_sandbox_route(self) -> None:
        fake_result = {
            "status": "success",
            "exit_code": 0,
            "stdout": "ok",
            "stderr": "",
            "duration_ms": 12,
            "blocked_reason": "",
            "code_hash": "abc",
            "signature": "sig",
            "audit_log_path": "data/audit/sandbox_audit.jsonl",
            "telemetry": {
                "cpu_usage_pct": 10.0,
                "memory_peak_mb": 32.0,
                "network_tx_kb": 0.0,
                "network_rx_kb": 0.0,
                "filesystem_events": [],
                "syscall_sequence": [],
                "abnormal_events": [],
            },
        }
        with patch("agent.graphs.subgraphs.sandbox.execute_untrusted_code", return_value=fake_result):
            result = self.dispatcher.dispatch(
                "sandbox_exec",
                {"user_id": "u1", "language": "python", "code": "print('ok')"},
            )
        self.assertEqual(result.get("type"), "sandbox_exec")
        self.assertEqual(result.get("status"), "success")

    def test_dispatcher_passes_through_state_errors(self) -> None:
        class _Graph:
            def invoke(self, _state):
                return {
                    "task_progress": [],
                    "result": {"type": "qa", "answer": "ok"},
                    "errors": ["mock error"],
                }

        dispatcher = TaskDispatcher(self.bus, graph=_Graph())
        result = dispatcher.dispatch("qa", {"query": "x"})
        self.assertEqual(result.get("type"), "qa")
        self.assertEqual(result.get("errors"), ["mock error"])


if __name__ == "__main__":
    unittest.main()
