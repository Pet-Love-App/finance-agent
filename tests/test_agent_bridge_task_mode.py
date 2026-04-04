from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


def _load_bridge_module():
    repo_root = Path(__file__).resolve().parents[1]
    module_path = repo_root / "desktop_app" / "agent_bridge" / "agent_chat_service.py"
    spec = importlib.util.spec_from_file_location("agent_chat_service", str(module_path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader = spec.loader
    assert loader is not None
    loader.exec_module(module)
    return module


class TestAgentBridgeTaskMode(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bridge = _load_bridge_module()

    def test_handle_request_task_type(self) -> None:
        response = self.bridge.handle_request(
            {
                "message": "执行任务",
                "payload": {
                    "task_type": "qa",
                    "task_payload": {"query": "报销需要哪些附件？"},
                },
            }
        )
        self.assertTrue(response.get("ok"))
        self.assertEqual(response.get("mode"), "task")
        self.assertEqual(response.get("task_type"), "qa")
        self.assertEqual(response.get("task_result", {}).get("type"), "qa")

    def test_handle_request_stream_task_type(self) -> None:
        events = list(
            self.bridge.handle_request_stream(
                {
                    "message": "执行任务",
                    "payload": {
                        "task_type": "budget",
                        "task_payload": {
                            "aggregate": {"total_amount": 1200, "count": 2, "by_month": []},
                            "strategy": {"growth_rate": 0.1},
                        },
                    },
                }
            )
        )
        self.assertTrue(len(events) >= 2)
        self.assertEqual(events[0].get("type"), "status")
        self.assertEqual(events[-1].get("type"), "done")
        done_resp = events[-1].get("response", {})
        self.assertTrue(done_resp.get("ok"))
        self.assertEqual(done_resp.get("task_type"), "budget")


if __name__ == "__main__":
    unittest.main()
