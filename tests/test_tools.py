from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
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

        @property
        def empty(self):
            return len(self._rows) == 0

        def __getitem__(self, key):
            return _FakeSeries([row.get(key, 0) for row in self._rows])

        def __setitem__(self, key, value):
            for row in self._rows:
                row[key] = value

        def groupby(self, key, as_index=False):
            return _FakeGroupBy(self._rows, key)

        def to_dict(self, orient="records"):
            if orient != "records":
                raise ValueError("Only records orient is supported in fake pandas")
            return [dict(row) for row in self._rows]

        def to_excel(self, path, index=False):
            Path(path).write_text(json.dumps(self._rows, ensure_ascii=False), encoding="utf-8")

    fake_pd = ModuleType("pandas")
    fake_pd.DataFrame = _FakeDataFrame
    sys.modules["pandas"] = fake_pd


_install_fake_pandas()

import agent.tools as tools
from agent.tools.doc_tools import (
    generate_email_draft,
    generate_excel_sheet,
    generate_word_doc,
    send_or_export_email,
)
from agent.tools.extraction_tools import (
    extract_invoice_fields,
    extract_text_from_files,
    ocr_extract,
    parse_activity,
)
from agent.tools.input_tools import classify_files, scan_inputs
from agent.tools.qa_tools import answer_generate, build_workflow_hint, question_understand
from agent.tools.rule_tools import check_rules, rag_retrieve, rule_retrieve
from agent.tools.stats_tools import (
    aggregate_records,
    budget_calculate,
    data_clean,
    generate_budget,
    generate_final_account,
    generate_report,
    load_final_data,
)
from agent.tools.storage_tools import load_records, save_record
from agent.graphs.subgraphs.budget import route_after_load_final_data
from agent.graphs.subgraphs.final_account import route_after_data_clean, route_after_load_records
from agent.graphs.subgraphs.qa import route_after_understand, rule_retrieve_node
from agent.graphs.subgraphs.reimburse import route_after_extract, route_after_rule_check, route_after_scan
from agent.kb.ingest import _infer_category
from agent import EventBus, TaskDispatcher


class TestToolExports(unittest.TestCase):
    def test_all_exported_tools_are_callable(self) -> None:
        for name in tools.__all__:
            self.assertTrue(hasattr(tools, name), f"缺少导出: {name}")
            self.assertTrue(callable(getattr(tools, name)), f"不可调用: {name}")


class TestInputTools(unittest.TestCase):
    def test_scan_and_classify_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            pdf = base / "a.pdf"
            img = base / "b.png"
            txt = base / "c.txt"
            pdf.write_text("fake-pdf", encoding="utf-8")
            img.write_text("fake-img", encoding="utf-8")
            txt.write_text("hello", encoding="utf-8")

            scanned = scan_inputs([str(base)])
            self.assertTrue(scanned.success)
            files = scanned.data.get("files", [])
            self.assertEqual(len(files), 3)

            classified = classify_files(files)
            self.assertTrue(classified.success)
            groups = classified.data["classified"]
            self.assertEqual(len(groups["pdf"]), 1)
            self.assertEqual(len(groups["image"]), 1)
            self.assertEqual(len(groups["text"]), 1)


class TestExtractionTools(unittest.TestCase):
    def test_extract_invoice_and_activity(self) -> None:
        invoice_res = extract_invoice_fields("发票号码: ABC123456 金额 88.50元 日期 2026-03-10")
        self.assertTrue(invoice_res.success)
        invoice = invoice_res.data["invoice"]
        self.assertEqual(invoice["invoice_no"], "ABC123456")
        self.assertEqual(invoice["amount"], 88.5)

        activity_res = parse_activity("活动时间 2026-03-10，地点: 六教，活动说明：测试")
        self.assertTrue(activity_res.success)
        self.assertIn("2026", activity_res.data["activity"]["activity_date"])

    def test_extract_text_from_files_with_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            txt_path = Path(tmp) / "note.txt"
            txt_path.write_text("文本内容", encoding="utf-8")

            classified = {
                "pdf": ["mock.pdf"],
                "image": ["mock.png"],
                "text": [str(txt_path)],
            }

            with patch("agent.tools.extraction_tools.extract_pdf_text") as mock_pdf, patch(
                "agent.tools.extraction_tools.ocr_extract"
            ) as mock_ocr:
                mock_pdf.return_value.success = False
                mock_pdf.return_value.data = {"text": ""}
                mock_ocr.return_value.success = True
                mock_ocr.return_value.data = {"text": "OCR文本"}

                res = extract_text_from_files(classified)
                self.assertTrue(res.success)
                merged = res.data["merged_text"]
                self.assertIn("OCR文本", merged)
                self.assertIn("文本内容", merged)

    def test_ocr_extract_import_failure(self) -> None:
        original_import = __import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "agent.parser.utils.ocr_utils":
                raise ImportError("mock missing")
            return original_import(name, globals, locals, fromlist, level)

        with patch("builtins.__import__", side_effect=fake_import):
            res = ocr_extract("dummy.png")
            self.assertFalse(res.success)
            self.assertTrue(res.fallback_used)


class TestRuleQATools(unittest.TestCase):
    def test_rule_check_and_retrieve(self) -> None:
        check_res = check_rules(
            invoice={"amount": 1200},
            activity={"activity_date": "2026-03-10"},
            rules={"max_amount": 1000},
        )
        self.assertTrue(check_res.success)
        self.assertFalse(check_res.data["compliance"])
        self.assertTrue(check_res.data["violations"])

        with tempfile.TemporaryDirectory() as tmp:
            rules_path = Path(tmp) / "rules.json"
            rules_path.write_text(json.dumps({"规则": "报销"}, ensure_ascii=False), encoding="utf-8")
            retrieve_res = rule_retrieve("报销", str(rules_path))
            self.assertTrue(retrieve_res.success)
            self.assertEqual(len(retrieve_res.data["items"]), 1)
            self.assertGreater(retrieve_res.data["items"][0]["score"], 0)

    def test_rule_retrieve_text_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rules_path = Path(tmp) / "rules.txt"
            rules_path.write_text(
                "餐饮发票需提供菜单。\n\n差旅报销需提供行程单。",
                encoding="utf-8",
            )
            retrieve_res = rule_retrieve("差旅报销", str(rules_path), top_k=2)
            self.assertTrue(retrieve_res.success)
            self.assertGreaterEqual(len(retrieve_res.data["items"]), 1)
            self.assertIn("差旅", retrieve_res.data["items"][0]["content"])

    def test_rag_and_qa(self) -> None:
        class _MockItem:
            def __init__(self) -> None:
                self.source = "kb"
                self.title = "条款A"
                self.content = "内容"
                self.score = 0.9

        with patch("agent.kb.retriever.search_policy", return_value=[_MockItem()]), patch(
            "agent.kb.retriever.format_retrieved_context", return_value="context"
        ):
            rag_res = rag_retrieve("报销", top_k=1)
            self.assertTrue(rag_res.success)
            self.assertEqual(len(rag_res.data["items"]), 1)
            self.assertEqual(rag_res.data["context"], "context")
            self.assertEqual(rag_res.data["retrieval"], "vector")

    def test_rag_retrieve_fallback_and_threshold(self) -> None:
        class _MockItem:
            def __init__(self, score: float) -> None:
                self.source = "kb"
                self.title = "条款A"
                self.content = "内容"
                self.score = score

        with patch("agent.kb.retriever.search_policy", side_effect=RuntimeError("boom")), patch(
            "agent.kb.retriever.retrieve_chunks", return_value=[_MockItem(0.4), _MockItem(0.9)]
        ):
            rag_res = rag_retrieve("报销", top_k=2, score_threshold=0.8)
            self.assertTrue(rag_res.success)
            self.assertEqual(rag_res.data["retrieval"], "keyword_fallback")
            self.assertEqual(len(rag_res.data["items"]), 1)

        intent_res = question_understand("报销需要哪些附件")
        self.assertTrue(intent_res.success)
        self.assertEqual(intent_res.data["intent"], "policy")

        ans_res = answer_generate("问题", [{"title": "条款A", "source": "kb", "score": 0.88}])
        self.assertTrue(ans_res.success)
        self.assertIn("条款A", ans_res.data["answer"])

    def test_answer_generate_low_confidence_needs_clarification(self) -> None:
        ans_res = answer_generate(
            "报销怎么填",
            [{"title": "弱相关条款", "source": "kb", "score": 0.21}],
            min_score=0.55,
            intent="policy",
        )
        self.assertTrue(ans_res.success)
        self.assertTrue(ans_res.data.get("needs_clarification"))
        self.assertTrue(bool(ans_res.data.get("clarifying_question")))

    def test_answer_generate_contains_category_hint(self) -> None:
        ans_res = answer_generate(
            "海外实践报销需要什么材料",
            [
                {
                    "title": "海外实践报销细则",
                    "source": "海外实践/未央书院 国际差旅财务报销培训（终版）V7.pptx",
                    "score": 0.92,
                    "category": "海外实践",
                    "doc_type": "pptx",
                }
            ],
            min_score=0.55,
            intent="policy",
        )
        self.assertTrue(ans_res.success)
        self.assertIn("海外实践", ans_res.data["answer"])
        self.assertEqual(ans_res.data["citations"][0]["category"], "海外实践")

    def test_answer_generate_returns_direct_answer_with_citation_labels(self) -> None:
        ans_res = answer_generate(
            "学生国内实践差旅报销所需材料有哪些",
            [
                {
                    "title": "书院财务报销规范-苗霖霖-202508-片段9",
                    "source": "书院财务报销规范-苗霖霖-202508.pptx",
                    "content": "三、学生国内实践差旅报销所需材料。交通费用：机票行程单或者机票发票、火车票。住宿费：发票及住宿水单。交通意外保险发票。租车费。",
                    "score": 0.93,
                    "category": "国内+思政实践",
                    "doc_type": "pptx",
                }
            ],
            min_score=0.55,
            intent="policy",
        )
        self.assertTrue(ans_res.success)
        self.assertIn("交通费用", ans_res.data["answer"])
        self.assertIn("住宿费", ans_res.data["answer"])
        self.assertIn("参考：书院财务报销规范-苗霖霖-202508.pptx", ans_res.data["answer"])
        self.assertNotIn("请参考", ans_res.data["answer"])

    def test_answer_generate_prefers_llm_synthesis_when_available(self) -> None:
        with patch("agent.tools.qa_tools._generate_llm_answer", return_value="可报销范围包括交通与住宿，先完成报备再提交材料。"):
            ans_res = answer_generate(
                "告诉我报销流程",
                [
                    {
                        "title": "书院财务报销规范-片段7",
                        "source": "书院财务报销规范-苗霖霖-202508.pptx",
                        "content": "先报备，再整理决算表和票据。",
                        "score": 0.91,
                        "category": "政策文件",
                        "doc_type": "pptx",
                    }
                ],
                min_score=0.55,
                intent="policy",
            )
        self.assertTrue(ans_res.success)
        self.assertIn("可报销范围包括交通与住宿", ans_res.data["answer"])
        self.assertIn("主要依据：书院财务报销规范-片段7", ans_res.data["answer"])
        self.assertNotIn("根据检索到的制度内容，整理如下", ans_res.data["answer"])

    def test_answer_generate_fallback_when_llm_unavailable(self) -> None:
        with patch("agent.tools.qa_tools._generate_llm_answer", return_value=None):
            ans_res = answer_generate(
                "学生国内实践差旅报销所需材料有哪些",
                [
                    {
                        "title": "书院财务报销规范-苗霖霖-202508-片段9",
                        "source": "书院财务报销规范-苗霖霖-202508.pptx",
                        "content": "交通费用：机票行程单或者机票发票。住宿费：发票及住宿水单。",
                        "score": 0.93,
                        "category": "国内+思政实践",
                        "doc_type": "pptx",
                    }
                ],
                min_score=0.55,
                intent="policy",
            )
        self.assertTrue(ans_res.success)
        self.assertIn("根据检索到的制度内容，整理如下", ans_res.data["answer"])
        self.assertIn("交通费用", ans_res.data["answer"])

    def test_build_workflow_hint(self) -> None:
        finance_hint = build_workflow_hint("帮我处理财务报销并自动填表")
        self.assertIsNotNone(finance_hint)
        self.assertEqual(finance_hint.get("name"), "finance_workflow")
        self.assertGreaterEqual(len(finance_hint.get("steps", [])), 3)


class TestKBIngestHelpers(unittest.TestCase):
    def test_infer_category(self) -> None:
        cat, sub = _infer_category("海外实践/合同补充协议模板.docx")
        self.assertEqual(cat, "海外实践")
        self.assertEqual(sub, "")
        cat2, sub2 = _infer_category("政策文件/2026/未央书院学生活动经费管理细则.pdf")
        self.assertEqual(cat2, "政策文件")
        self.assertEqual(sub2, "2026")


class TestDocStorageStatsTools(unittest.TestCase):
    def test_doc_tools(self) -> None:
        draft_res = generate_email_draft(
            activity={"activity_date": "2026-03-10", "location": "六教"},
            summary={"total_amount": 500},
            attachments=["a.docx"],
        )
        self.assertTrue(draft_res.success)

        with tempfile.TemporaryDirectory() as tmp:
            eml_res = send_or_export_email(draft_res.data["draft"], output_dir=tmp)
            self.assertTrue(eml_res.success)
            self.assertTrue(Path(eml_res.data["eml_path"]).exists())

            excel_res = generate_excel_sheet(
                invoices=[{"invoice_no": "A1", "amount": 10}],
                activity={"activity_date": "2026-03-10"},
                output_dir=tmp,
            )
            self.assertTrue(excel_res.success)
            self.assertTrue(Path(excel_res.data["excel_path"]).exists())

    def test_generate_word_doc_import_failure(self) -> None:
        original_import = __import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "docx":
                raise ImportError("mock missing")
            return original_import(name, globals, locals, fromlist, level)

        with patch("builtins.__import__", side_effect=fake_import):
            res = generate_word_doc(activity={}, invoices=[])
            self.assertFalse(res.success)

    def test_storage_and_stats_tools(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "records.db")
            record = {"invoice": {"amount": 100}, "activity": {"activity_date": "2026-03-10"}}
            save_res = save_record(record, db_path=db_path)
            self.assertTrue(save_res.success)

            load_res = load_records({}, db_path=db_path)
            self.assertTrue(load_res.success)
            self.assertGreaterEqual(len(load_res.data["records"]), 1)

            records = load_res.data["records"]
            clean_res = data_clean(records)
            self.assertTrue(clean_res.success)

            agg_res = aggregate_records(clean_res.data["cleaned"])
            self.assertTrue(agg_res.success)
            aggregate = agg_res.data["aggregate"]

            final_data_res = load_final_data({"aggregate": aggregate})
            self.assertTrue(final_data_res.success)

            budget_res = budget_calculate(final_data_res.data["final_data"], {"growth_rate": 0.1})
            self.assertTrue(budget_res.success)

            final_res = generate_final_account(aggregate, output_dir=tmp)
            self.assertTrue(final_res.success)
            self.assertTrue(Path(final_res.data["final_account_path"]).exists())

            budget_file_res = generate_budget(budget_res.data["budget"], output_dir=tmp)
            self.assertTrue(budget_file_res.success)
            self.assertTrue(Path(budget_file_res.data["budget_path"]).exists())

            report_res = generate_report(aggregate, budget_res.data["budget"], output_dir=tmp)
            self.assertTrue(report_res.success)
            self.assertTrue(Path(report_res.data["report_path"]).exists())


class TestReimburseRouting(unittest.TestCase):
    def test_route_after_scan(self) -> None:
        self.assertEqual(route_after_scan({"files": ["a.pdf"]}), "ClassifyFileNode")
        self.assertEqual(route_after_scan({"files": []}), "SaveRecordNode")

    def test_route_after_extract(self) -> None:
        self.assertEqual(route_after_extract({"merged_text": "文本"}), "InvoiceExtractNode")
        self.assertEqual(route_after_extract({"merged_text": "   "}), "ActivityParseNode")

    def test_route_after_rule_check(self) -> None:
        state = {
            "payload": {"stop_on_rule_violation": True},
            "rule_result": {"compliance": False},
        }
        self.assertEqual(route_after_rule_check(state), "SaveRecordNode")
        state_ok = {
            "payload": {"stop_on_rule_violation": False},
            "rule_result": {"compliance": False},
        }
        self.assertEqual(route_after_rule_check(state_ok), "GenDocNode")
        policy_state = {
            "payload": {"graph_policy": {"reimburse_stop_on_rule_violation": True}},
            "rule_result": {"compliance": False},
        }
        self.assertEqual(route_after_rule_check(policy_state), "SaveRecordNode")


class TestOtherSubgraphRouting(unittest.TestCase):
    def test_route_after_understand(self) -> None:
        self.assertEqual(route_after_understand({"payload": {"normalized_query": "报销附件"}}), "RuleRetrieveNode")
        self.assertEqual(route_after_understand({"payload": {"normalized_query": "  "}}), "QAFallbackNode")
        self.assertEqual(
            route_after_understand({"payload": {"normalized_query": "  ", "graph_policy": {"qa_allow_empty_query": True}}}),
            "RuleRetrieveNode",
        )

    def test_rule_retrieve_node_appends_clarification_to_answer(self) -> None:
        with patch("agent.graphs.subgraphs.qa.rule_retrieve") as mock_rule_retrieve, patch(
            "agent.graphs.subgraphs.qa.answer_generate"
        ) as mock_answer_generate, patch("agent.graphs.subgraphs.qa.build_workflow_hint") as mock_workflow_hint:
            mock_rule_retrieve.return_value.data = {"items": []}
            mock_rule_retrieve.return_value.error = None
            mock_answer_generate.return_value.data = {
                "answer": "证据不足，暂不下结论。",
                "citations": [],
                "confidence": 0.2,
                "needs_clarification": True,
                "clarifying_question": "活动类型、票据类型、金额区间分别是什么？",
            }
            mock_answer_generate.return_value.error = None
            mock_workflow_hint.return_value = None

            state = {"payload": {"normalized_query": "报销怎么做"}, "errors": [], "task_progress": []}
            out = rule_retrieve_node(state)
            answer = out.get("result", {}).get("answer", "")
            self.assertIn("证据不足", answer)
            self.assertIn("请补充", answer)
            self.assertTrue(out.get("result", {}).get("needs_clarification"))

    def test_route_after_load_records(self) -> None:
        self.assertEqual(route_after_load_records({"records": [{"id": 1}]}), "DataCleanNode")
        self.assertEqual(route_after_load_records({"records": []}), "FinalGenerateNode")
        self.assertEqual(
            route_after_load_records({"records": [], "payload": {"graph_policy": {"final_generate_when_empty": False}}}),
            "DataCleanNode",
        )

    def test_route_after_data_clean(self) -> None:
        self.assertEqual(route_after_data_clean({"records": [{"id": 1}]}), "DataAggregateNode")
        self.assertEqual(route_after_data_clean({"records": []}), "FinalGenerateNode")
        self.assertEqual(
            route_after_data_clean({"records": [], "payload": {"graph_policy": {"final_generate_when_empty": False}}}),
            "DataAggregateNode",
        )

    def test_route_after_load_final_data(self) -> None:
        self.assertEqual(route_after_load_final_data({"aggregate": {"total_amount": 100.0}}), "BudgetCalculateNode")
        self.assertEqual(route_after_load_final_data({"aggregate": {}}), "BudgetGenerateNode")
        self.assertEqual(
            route_after_load_final_data({"aggregate": {}, "payload": {"graph_policy": {"budget_skip_calculate_when_empty": False}}}),
            "BudgetCalculateNode",
        )


class TestDispatcherGraphPolicy(unittest.TestCase):
    def test_dispatcher_injects_default_graph_policy(self) -> None:
        class _Graph:
            def invoke(self, state):
                policy = state.get("payload", {}).get("graph_policy", {})
                return {"task_progress": [], "result": {"type": "qa", "policy_keys": sorted(policy.keys())}, "errors": []}

        dispatcher = TaskDispatcher(EventBus(), graph=_Graph())
        result = dispatcher.dispatch("qa", {"query": "报销规则"})
        keys = result.get("policy_keys", [])
        self.assertIn("qa_kb_top_k", keys)
        self.assertIn("reimburse_stop_on_rule_violation", keys)
        self.assertIn("graph_enable_trace", keys)

    def test_dispatcher_graph_policy_user_override(self) -> None:
        class _Graph:
            def invoke(self, state):
                policy = state.get("payload", {}).get("graph_policy", {})
                return {"task_progress": [], "result": {"type": "qa", "top_k": policy.get("qa_kb_top_k")}, "errors": []}

        dispatcher = TaskDispatcher(EventBus(), graph=_Graph())
        result = dispatcher.dispatch("qa", {"query": "报销规则", "graph_policy": {"qa_kb_top_k": 9}})
        self.assertEqual(result.get("top_k"), 9)


if __name__ == "__main__":
    unittest.main()
