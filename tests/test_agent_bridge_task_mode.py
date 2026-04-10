from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
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
        try:
            self.bridge.stop_memory_flush_thread()
        except Exception:
            pass
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
            task_result = response.get("task_result", {}) if isinstance(response.get("task_result", {}), dict) else {}
            errors = task_result.get("errors", []) if isinstance(task_result.get("errors", []), list) else []
            self.assertEqual(response.get("mode"), "task")
            self.assertEqual(response.get("task_type"), "auto")
            self.assertIn("partial_failed", str(task_result.get("status", "")))
            self.assertTrue(any("材料不完整" in str(item) for item in errors) or "材料不完整" in reply)
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
            task_result = response.get("task_result", {}) if isinstance(response.get("task_result", {}), dict) else {}
            logs = task_result.get("logs", []) if isinstance(task_result.get("logs", []), list) else []
            self.assertEqual(response.get("mode"), "task")
            self.assertEqual(response.get("task_type"), "auto")
            self.assertIn("completed", str(task_result.get("status", "")))
            self.assertTrue(any("已生成压缩包" in str(item) for item in logs) or "已生成压缩包" in reply)

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
            task_result = response.get("task_result", {}) if isinstance(response.get("task_result", {}), dict) else {}
            errors = task_result.get("errors", []) if isinstance(task_result.get("errors", []), list) else []
            self.assertEqual(response.get("mode"), "task")
            self.assertEqual(response.get("task_type"), "auto")
            self.assertIn("partial_failed", str(task_result.get("status", "")))
            self.assertTrue(any("合同材料" in str(item) for item in errors) or "合同材料" in reply)
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

    def test_extract_workspace_plan_with_invalid_json_windows_path(self) -> None:
        planner_raw = (
            '{ "reply": "请提供具体文件路径和修改内容，例如：'
            "'E:\\Desktop\\agent\\agent.py 修改为...' 或 '这个文件/当前文件 修改为...'。",
            ' "actions": [] }'
        )

        parsed = self.bridge._extract_workspace_plan(planner_raw)
        self.assertIsInstance(parsed, dict)
        self.assertIn("请提供具体文件路径和修改内容", str(parsed.get("reply", "")))
        self.assertEqual(parsed.get("actions"), [])

    def test_workspace_mode_chat_message_routes_to_llm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            llm_reply = "这是一个普通问答回复"

            with patch.object(self.bridge, "_is_llm_enabled", return_value=True), patch.object(
                self.bridge, "_llm_chat", return_value=llm_reply
            ):
                response = self.bridge.handle_request(
                    {
                        "message": "你好",
                        "payload": {
                            "workspace_mode": True,
                            "workspace_dir": str(root),
                        },
                    }
                )

            reply = str(response.get("reply", ""))
            self.assertTrue(response.get("ok"))
            self.assertEqual(response.get("mode"), "task")
            self.assertEqual(response.get("task_type"), "auto")
            self.assertTrue(bool(reply.strip()))

    def test_supervisor_auto_routes_recon_to_task_mode(self) -> None:
        with patch.object(
            self.bridge,
            "_run_v2_task",
            return_value={"mode": "task", "task_type": "recon", "reply": "预算/决算核对完成：状态=warning"},
        ):
            response = self.bridge.handle_request(
                {
                    "message": "请帮我核对预算表和决算表差异",
                    "payload": {},
                }
            )
        self.assertTrue(response.get("ok"))
        self.assertEqual(response.get("mode"), "task")
        self.assertEqual(response.get("task_type"), "recon")

    def test_format_task_reply_for_recon(self) -> None:
        result = {
            "type": "recon",
            "status": "warning",
            "summary": {"total_items": 8, "blocking": 1, "warning": 2, "hint": 1},
            "blocking_items": [
                {
                    "key": "2026-01|交通费",
                    "abs_diff": 1200,
                    "pct_diff": 0.2,
                    "reason": "超出阻断阈值",
                }
            ],
            "warning_items": [
                {
                    "key": "2026-02|物料费",
                    "abs_diff": 80,
                    "pct_diff": 0.06,
                    "reason": "超出预警阈值",
                }
            ],
        }
        reply = self.bridge._format_task_reply("recon", result)
        self.assertIn("预算/决算核对完成", reply)
        self.assertIn("阻断 1 项", reply)
        self.assertIn("预警 2 项", reply)
        self.assertIn("阻断项明细", reply)
        self.assertIn("2026-01|交通费", reply)
        self.assertIn("预警项明细", reply)
        self.assertIn("建议处理", reply)
        self.assertIn("优先复核金额来源与汇总口径", reply)

    def test_format_task_reply_for_recon_detail_limit(self) -> None:
        result = {
            "type": "recon",
            "status": "failed",
            "summary": {"total_items": 3, "blocking": 3, "warning": 0, "hint": 0},
            "detail_limit": 1,
            "blocking_items": [
                {"key": "A", "abs_diff": 1, "pct_diff": 0.1, "reason": "r1"},
                {"key": "B", "abs_diff": 2, "pct_diff": 0.2, "reason": "r2"},
            ],
        }
        reply = self.bridge._format_task_reply("recon", result)
        self.assertIn("A：差额=1", reply)
        self.assertNotIn("B：差额=2", reply)
        self.assertIn("建议处理", reply)

    def test_format_task_reply_for_recon_custom_suggestion_rules(self) -> None:
        result = {
            "type": "recon",
            "status": "warning",
            "summary": {"total_items": 2, "blocking": 0, "warning": 1, "hint": 0},
            "warning_items": [
                {"key": "税率项", "abs_diff": 10, "pct_diff": 0.03, "reason": "税率口径不一致"},
            ],
            "suggestion_rules": [
                {
                    "reason_contains": ["税率", "口径"],
                    "suggestion": "请先统一税率与含税口径，再重新执行核对。",
                }
            ],
        }
        reply = self.bridge._format_task_reply("recon", result)
        self.assertIn("建议处理", reply)
        self.assertIn("请先统一税率与含税口径，再重新执行核对。", reply)

    def test_format_task_reply_for_recon_clarification(self) -> None:
        result = {
            "type": "recon",
            "status": "needs_clarification",
            "message": "请补充预算与决算数据",
        }
        reply = self.bridge._format_task_reply("recon", result)
        self.assertEqual(reply, "请补充预算与决算数据")

    def test_run_audit_uses_v2_dispatcher_and_returns_compatible_report(self) -> None:
        fake_recon_result = {
            "type": "recon",
            "status": "warning",
            "summary": {"total_items": 3, "blocking": 1, "warning": 1, "hint": 0},
            "differences": [
                {"key": "2026-01|交通费", "abs_diff": 1200, "pct_diff": 0.2, "reason": "超出阻断阈值"},
                {"key": "2026-02|物料费", "abs_diff": 80, "pct_diff": 0.06, "reason": "超出预警阈值"},
            ],
            "blocking_items": [
                {"key": "2026-01|交通费", "abs_diff": 1200, "pct_diff": 0.2, "reason": "超出阻断阈值"}
            ],
            "warning_items": [
                {"key": "2026-02|物料费", "abs_diff": 80, "pct_diff": 0.06, "reason": "超出预警阈值"}
            ],
            "errors": [],
        }
        with patch("agent.core.dispatcher.TaskDispatcher.dispatch", return_value=fake_recon_result):
            result = self.bridge._run_audit(
                budget_source={"rows": [{"month": "2026-01", "amount": 1000}]},
                actual_source={"rows": [{"month": "2026-01", "amount": 2200}]},
            )

        self.assertIn("审计完成", str(result.get("reply", "")))
        report_json = result.get("report_json", {})
        self.assertEqual(report_json.get("summary", {}).get("overall_status"), "WARNING")
        self.assertEqual(int(report_json.get("summary", {}).get("high_risk_issues", 0)), 1)
        self.assertEqual(len(report_json.get("discrepancies", [])), 2)
        self.assertIn("预算/决算核对报告", str(result.get("report_markdown", "")))

    def test_format_task_reply_for_confirmation(self) -> None:
        result = {
            "type": "confirmation",
            "status": "pending_confirmation",
            "message": "检测到高风险写操作，请先确认。",
        }
        reply = self.bridge._format_task_reply("auto", result)
        self.assertEqual(reply, "检测到高风险写操作，请先确认。")

    def test_format_task_reply_for_file_edit_needs_clarification(self) -> None:
        result = {
            "type": "file_edit",
            "status": "needs_clarification",
            "message": "未检测到可执行文件操作，请补充目标文件路径与具体修改内容后重试。",
            "changeset": [],
        }
        reply = self.bridge._format_task_reply("auto", result)
        self.assertIn("补充目标文件路径", reply)

    def test_supervisor_auto_routes_file_edit_to_task_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            response = self.bridge.handle_request(
                {
                    "message": "/write notes.txt\nhello",
                    "payload": {
                        "workspace_mode": True,
                        "workspace_dir": str(root),
                    },
                }
            )
            self.assertTrue(response.get("ok"))
            self.assertEqual(response.get("mode"), "task")
            self.assertEqual(response.get("task_type"), "auto")


if __name__ == "__main__":
    unittest.main()
