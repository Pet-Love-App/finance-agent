from __future__ import annotations

import tempfile
import unittest
import json
from pathlib import Path

from agent.graphs.contracts import describe_graph_contract
from agent.graphs.names import ALL_GRAPH_NODES, INTENT_ROUTE_TARGETS
from agent.graphs.intent import intent_node, route_by_task
from agent.graphs.spec import build_conditional_route_snapshot
from agent.graphs.subgraphs.budget import route_after_load_final_data
from agent.graphs.subgraphs.final_account import final_generate_node
from agent.graphs.subgraphs.file_edit import file_edit_gateway_node
from agent.graphs.subgraphs.final_account import route_after_data_clean, route_after_load_records
from agent.graphs.subgraphs.reimburse import route_after_extract, route_after_scan
from agent.graphs.task_registry import get_start_node_for_runtime_task, normalize_task_alias


class TestSupervisorRouter(unittest.TestCase):
    def test_graph_contract_snapshot_up_to_date(self) -> None:
        snapshot_path = Path(__file__).resolve().parents[1] / "agent" / "graphs" / "graph_contract_snapshot.json"
        self.assertTrue(snapshot_path.exists(), "缺少图契约快照文件，请执行 scripts/update_graph_contract_snapshot.py")
        expected = describe_graph_contract()
        actual = json.loads(snapshot_path.read_text(encoding="utf-8"))
        self.assertDictEqual(actual, expected)

    def test_conditional_route_snapshot(self) -> None:
        snapshot = build_conditional_route_snapshot()
        self.assertIn("intent", snapshot)
        self.assertIn("reimburse.scan", snapshot)
        self.assertIn("budget.load_final_data", snapshot)
        self.assertIn("IntentClarifyNode", snapshot["intent"]["targets"])
        self.assertIn("IntentConfirmNode", snapshot["intent"]["targets"])

    def test_all_graph_nodes_contract(self) -> None:
        required_nodes = {
            "IntentNode",
            "IntentClarifyNode",
            "IntentConfirmNode",
            "ReimburseStartNode",
            "ScanFileNode",
            "ClassifyFileNode",
            "ExtractNode",
            "InvoiceExtractNode",
            "ActivityParseNode",
            "RuleCheckNode",
            "GenDocNode",
            "GenMailNode",
            "SaveRecordNode",
            "ReimburseFailNode",
            "QAStartNode",
            "QuestionUnderstandNode",
            "RuleRetrieveNode",
            "QAFallbackNode",
            "FinalStartNode",
            "LoadRecordNode",
            "DataCleanNode",
            "DataAggregateNode",
            "FinalGenerateNode",
            "FinalFailNode",
            "BudgetStartNode",
            "LoadFinalDataNode",
            "BudgetCalculateNode",
            "BudgetGenerateNode",
            "BudgetFailNode",
            "SandboxStartNode",
            "SandboxExecuteNode",
            "FileEditStartNode",
            "FileEditGatewayNode",
        }
        self.assertSetEqual(set(ALL_GRAPH_NODES), required_nodes)

    def test_intent_route_targets_contract(self) -> None:
        required_targets = {
            "IntentClarifyNode",
            "IntentConfirmNode",
            "ReimburseStartNode",
            "QAStartNode",
            "FinalStartNode",
            "BudgetStartNode",
            "SandboxStartNode",
            "FileEditStartNode",
        }
        self.assertSetEqual(set(INTENT_ROUTE_TARGETS), required_targets)

    def test_intent_node_recon_classification(self) -> None:
        state = {
            "payload": {"query": "请核对预算表和决算表差异"},
            "task_progress": [],
        }
        updated = intent_node(state)
        self.assertEqual(updated.get("task_type"), "final_account")
        route_decision = updated.get("route_decision", {})
        self.assertEqual(route_decision.get("task_type"), "recon")
        self.assertGreaterEqual(float(route_decision.get("confidence", 0.0)), 0.8)
        self.assertIn("R201_RECON", route_decision.get("reason_codes", []))

    def test_intent_node_explicit_budget_fill(self) -> None:
        state = {
            "task_type": "t4_budget_fill",
            "payload": {"query": "请填写预算表"},
            "task_progress": [],
        }
        updated = intent_node(state)
        self.assertEqual(updated.get("task_type"), "budget")
        route_decision = updated.get("route_decision", {})
        self.assertEqual(route_decision.get("task_type"), "budget_fill")
        self.assertEqual(route_decision.get("confidence"), 1.0)
        self.assertTrue(bool(route_decision.get("requires_confirmation")))

    def test_route_by_task_file_edit(self) -> None:
        self.assertEqual(route_by_task({"task_type": "file_edit"}), "FileEditStartNode")

    def test_task_registry_alias_and_runtime_start_mapping(self) -> None:
        self.assertEqual(normalize_task_alias("t4_budget_fill"), "budget_fill")
        self.assertEqual(normalize_task_alias("T6_FILE_EDIT"), "file_edit")
        self.assertEqual(get_start_node_for_runtime_task("budget"), "BudgetStartNode")
        self.assertEqual(get_start_node_for_runtime_task("final_account"), "FinalStartNode")

    def test_route_by_task_clarification_guard(self) -> None:
        route = route_by_task(
            {
                "task_type": "reimburse",
                "route_decision": {"clarification_required": True},
            }
        )
        self.assertEqual(route, "IntentClarifyNode")

    def test_route_by_task_confirmation_guard(self) -> None:
        route = route_by_task(
            {
                "task_type": "file_edit",
                "payload": {"policy": {"confirmed": False}},
                "route_decision": {"requires_confirmation": True},
            }
        )
        self.assertEqual(route, "IntentConfirmNode")

    def test_intent_node_injects_confirmation_policy(self) -> None:
        state = {
            "payload": {"query": "帮我修改文件并写入内容"},
            "task_progress": [],
        }
        updated = intent_node(state)
        policy = updated.get("payload", {}).get("policy", {})
        self.assertFalse(bool(policy.get("requires_confirmation")))
        self.assertFalse(bool(policy.get("confirmed")))

    def test_intent_node_file_edit_text_samples(self) -> None:
        samples = [
            (
                "把这个文件里面加入5条测试数据",
                "R602_FILE_EDIT",
            ),
            (
                "AI Agent 任务已完成：auto。请编辑文件并修复任务类型判断。",
                "R602_FILE_EDIT",
            ),
            (
                "任务结果 任务类型: 报销问答。编辑文件并没有成功，任务类型判断也不正确。",
                "R602_FILE_EDIT",
            ),
            (
                "请在当前文件追加5条测试数据，并修正路由识别。",
                "R602_FILE_EDIT",
            ),
            (
                "write_file path=tests/test_supervisor_router.py content=append_cases",
                "R601_TOOL_ACTION",
            ),
        ]
        for query, expected_reason in samples:
            with self.subTest(query=query):
                updated = intent_node({"payload": {"query": query}, "task_progress": []})
                self.assertEqual(updated.get("task_type"), "file_edit")
                route_decision = updated.get("route_decision", {})
                self.assertEqual(route_decision.get("task_type"), "file_edit")
                self.assertNotEqual(route_decision.get("task_type"), "qa")
                self.assertIn(expected_reason, route_decision.get("reason_codes", []))

    def test_intent_node_prefers_action_plan_for_file_edit(self) -> None:
        updated = intent_node(
            {
                "payload": {
                    "query": "开始执行结构化任务",
                    "actions": [{"action": "organize_reimbursement_package", "package_name": "x.zip"}],
                },
                "task_progress": [],
            }
        )
        self.assertEqual(updated.get("task_type"), "file_edit")
        route_decision = updated.get("route_decision", {})
        self.assertEqual(route_decision.get("task_type"), "file_edit")
        self.assertIn("R605_ACTION_PLAN", route_decision.get("reason_codes", []))

    def test_file_edit_gateway_node(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            state = {
                "payload": {
                    "workspace_root": str(root),
                    "operation_id": "op-test-1",
                    "policy": {"requires_confirmation": False},
                    "actions": [
                        {
                            "action": "write_file",
                            "path": "notes/result.txt",
                            "content": "hello gateway",
                        }
                    ],
                },
                "task_progress": [],
                "errors": [],
            }
            updated = file_edit_gateway_node(state)
            result = updated.get("result", {})
            self.assertEqual(result.get("type"), "file_edit")
            self.assertEqual(result.get("status"), "completed")
            target = root / "notes" / "result.txt"
            self.assertTrue(target.exists())
            self.assertEqual(target.read_text(encoding="utf-8"), "hello gateway")

    def test_file_edit_gateway_uses_route_decision_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            state = {
                "payload": {
                    "workspace_root": str(root),
                    "operation_id": "op-test-2",
                    "actions": [
                        {
                            "action": "write_file",
                            "path": "notes/pending.txt",
                            "content": "blocked",
                        }
                    ],
                },
                "route_decision": {"requires_confirmation": True},
                "task_progress": [],
                "errors": [],
            }
            updated = file_edit_gateway_node(state)
            result = updated.get("result", {})
            self.assertEqual(result.get("status"), "pending_confirmation")

    def test_file_edit_gateway_needs_clarification_when_no_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            state = {
                "payload": {
                    "workspace_root": str(root),
                    "operation_id": "op-test-3",
                },
                "task_progress": [],
                "errors": [],
            }
            updated = file_edit_gateway_node(state)
            result = updated.get("result", {})
            self.assertEqual(result.get("type"), "file_edit")
            self.assertEqual(result.get("status"), "needs_clarification")
            self.assertIn("补充目标文件路径", str(result.get("message", "")))

    def test_fail_fast_routes(self) -> None:
        self.assertEqual(route_after_scan({"errors": ["scan failed"], "files": []}), "ReimburseFailNode")
        self.assertEqual(route_after_extract({"errors": ["extract failed"], "merged_text": ""}), "ReimburseFailNode")
        self.assertEqual(route_after_load_records({"errors": ["db failed"], "records": []}), "FinalFailNode")
        self.assertEqual(route_after_data_clean({"errors": ["clean failed"], "records": []}), "FinalFailNode")
        self.assertEqual(route_after_load_final_data({"errors": ["load failed"], "aggregate": {}}), "BudgetFailNode")

    def test_recon_result_with_structured_differences(self) -> None:
        state = {
            "route_decision": {"task_type": "recon"},
            "payload": {
                "budget_source": {
                    "rows": [
                        {"month": "2026-01", "amount": 1000},
                        {"month": "2026-02", "amount": 1000},
                    ]
                },
                "actual_source": {
                    "rows": [
                        {"month": "2026-01", "amount": 2000},
                        {"month": "2026-02", "amount": 900},
                    ]
                },
                "recon_policy": {
                    "abs_threshold": 50,
                    "pct_threshold": 0.05,
                    "suggestion_rules": [
                        {
                            "reason_contains": ["阈值"],
                            "suggestion": "请先复核阈值相关差异。",
                        }
                    ],
                },
            },
            "errors": [],
            "task_progress": [],
        }
        updated = final_generate_node(state)
        result = updated.get("result", {})
        self.assertEqual(result.get("type"), "recon")
        self.assertIn(result.get("status"), {"failed", "warning", "passed_with_hint", "passed"})
        summary = result.get("summary", {})
        self.assertGreaterEqual(int(summary.get("total_items", 0)), 2)
        self.assertGreaterEqual(int(summary.get("warning", 0)) + int(summary.get("blocking", 0)), 1)
        self.assertIsInstance(result.get("suggestion_rules"), list)
        self.assertEqual(result.get("suggestion_rules")[0].get("suggestion"), "请先复核阈值相关差异。")

    def test_recon_result_needs_clarification_when_no_data(self) -> None:
        state = {
            "route_decision": {"task_type": "recon"},
            "payload": {},
            "errors": [],
            "task_progress": [],
        }
        updated = final_generate_node(state)
        result = updated.get("result", {})
        self.assertEqual(result.get("type"), "recon")
        self.assertEqual(result.get("status"), "needs_clarification")


if __name__ == "__main__":
    unittest.main()
