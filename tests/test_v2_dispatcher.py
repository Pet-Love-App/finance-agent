from __future__ import annotations

import unittest
from pathlib import Path
import sys

repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

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


if __name__ == "__main__":
    unittest.main()
