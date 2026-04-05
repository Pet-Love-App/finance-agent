from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
import zipfile


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

    def setUp(self) -> None:
        self._memory_env_backup = os.environ.get("AGENT_MEMORY_PATH")
        self._memory_tmp_dir = tempfile.TemporaryDirectory()
        os.environ["AGENT_MEMORY_PATH"] = str(Path(self._memory_tmp_dir.name) / "agent_memory_test.json")

    def tearDown(self) -> None:
        if self._memory_env_backup is None:
            os.environ.pop("AGENT_MEMORY_PATH", None)
        else:
            os.environ["AGENT_MEMORY_PATH"] = self._memory_env_backup
        self._memory_tmp_dir.cleanup()

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

    def test_workspace_reimbursement_package_missing_required(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "报销单.xlsx").write_text("stub", encoding="utf-8")
            (root / "费用明细.xlsx").write_text("stub", encoding="utf-8")

            response = self.bridge.handle_request(
                {
                    "message": "请自动整理报销材料并生成压缩包",
                    "payload": {
                        "workspace_mode": True,
                        "workspace_dir": str(root),
                    },
                }
            )

            self.assertTrue(response.get("ok"))
            reply = str(response.get("reply", ""))
            self.assertIn("材料不完整", reply)
            self.assertIn("缺少：发票", reply)
            self.assertIn("缺少：支付凭证", reply)
            self.assertFalse(any(path.suffix.lower() == ".zip" for path in root.iterdir()))

    def test_workspace_reimbursement_package_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "报销单.xlsx").write_text("stub", encoding="utf-8")
            (root / "发票.pdf").write_text("stub", encoding="utf-8")
            (root / "支付回单.jpg").write_text("stub", encoding="utf-8")
            (root / "费用明细.xlsx").write_text("stub", encoding="utf-8")
            (root / "活动说明.docx").write_text("stub", encoding="utf-8")

            response = self.bridge.handle_request(
                {
                    "message": "请自动整理报销材料并打包成 my_pack.zip",
                    "payload": {
                        "workspace_mode": True,
                        "workspace_dir": str(root),
                    },
                }
            )

            self.assertTrue(response.get("ok"))
            reply = str(response.get("reply", ""))
            self.assertIn("已生成压缩包", reply)

            zip_path = root / "my_pack.zip"
            self.assertTrue(zip_path.exists())
            with zipfile.ZipFile(zip_path, mode="r") as zf:
                names = set(zf.namelist())
                self.assertIn("报销单/报销单.xlsx", names)
                self.assertIn("发票/发票.pdf", names)
                self.assertIn("支付凭证/支付回单.jpg", names)
                self.assertIn("费用明细/费用明细.xlsx", names)

    def test_workspace_reimbursement_package_custom_required(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "报销单.xlsx").write_text("stub", encoding="utf-8")
            (root / "发票.pdf").write_text("stub", encoding="utf-8")
            (root / "支付回单.jpg").write_text("stub", encoding="utf-8")
            (root / "费用明细.xlsx").write_text("stub", encoding="utf-8")

            response = self.bridge.handle_request(
                {
                    "message": "开始执行结构化任务",
                    "payload": {
                        "workspace_mode": True,
                        "workspace_dir": str(root),
                        "workspace_task": "reimbursement_package",
                        "package_name": "custom_pack.zip",
                        "reimbursement_package_options": {
                            "required_categories": ["报销单", "发票", "合同材料"],
                            "category_keywords": {
                                "合同材料": ["合同", "contract"],
                            },
                            "missing_suggestions": {
                                "合同材料": "示例：采购合同.pdf",
                            },
                        },
                    },
                }
            )

            self.assertTrue(response.get("ok"))
            reply = str(response.get("reply", ""))
            self.assertIn("材料不完整", reply)
            self.assertIn("缺少：合同材料", reply)
            self.assertIn("采购合同.pdf", reply)
            self.assertFalse((root / "custom_pack.zip").exists())

    def test_memory_writes_long_term_fact(self) -> None:
        payload = {"workspace_dir": "C:/demo/workspace"}
        self.bridge.handle_request(
            {
                "message": "请记住：我偏好简洁回答",
                "payload": payload,
            }
        )

        store = self.bridge._load_memory_store()
        session_key = self.bridge._memory_session_key(payload)
        session = store.get("sessions", {}).get(session_key, {})
        facts = [str(item.get("fact", "")) for item in session.get("long_term", []) if isinstance(item, dict)]
        self.assertTrue(any("简洁回答" in fact for fact in facts))

    def test_memory_reset_clears_previous_long_term(self) -> None:
        payload = {"workspace_dir": "C:/demo/workspace"}
        self.bridge.handle_request(
            {
                "message": "请记住：我的输出偏好是表格化",
                "payload": payload,
            }
        )
        self.bridge.handle_request(
            {
                "message": "你好",
                "payload": {**payload, "memory_reset": True},
            }
        )

        store = self.bridge._load_memory_store()
        session_key = self.bridge._memory_session_key(payload)
        session = store.get("sessions", {}).get(session_key, {})
        facts = [str(item.get("fact", "")) for item in session.get("long_term", []) if isinstance(item, dict)]
        self.assertFalse(any("表格化" in fact for fact in facts))

    def test_memory_disabled_no_write(self) -> None:
        payload = {"workspace_dir": "C:/demo/workspace", "memory_enabled": False}
        self.bridge.handle_request(
            {
                "message": "请记住：我喜欢分点回答",
                "payload": payload,
            }
        )
        memory_path = self.bridge._memory_path()
        self.assertFalse(memory_path.exists())

    def test_memory_workspace_isolated(self) -> None:
        payload_a = {"workspace_dir": "C:/workspace/a"}
        payload_b = {"workspace_dir": "C:/workspace/b"}

        self.bridge.handle_request({"message": "请记住：项目A需要日报", "payload": payload_a})
        self.bridge.handle_request({"message": "请记住：项目B需要周报", "payload": payload_b})

        store = self.bridge._load_memory_store()
        session_a = store.get("sessions", {}).get(self.bridge._memory_session_key(payload_a), {})
        session_b = store.get("sessions", {}).get(self.bridge._memory_session_key(payload_b), {})
        facts_a = [str(item.get("fact", "")) for item in session_a.get("long_term", []) if isinstance(item, dict)]
        facts_b = [str(item.get("fact", "")) for item in session_b.get("long_term", []) if isinstance(item, dict)]
        self.assertTrue(any("项目A" in fact for fact in facts_a))
        self.assertFalse(any("项目B" in fact for fact in facts_a))
        self.assertTrue(any("项目B" in fact for fact in facts_b))


if __name__ == "__main__":
    unittest.main()
