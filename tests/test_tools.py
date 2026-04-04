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
from agent.tools.qa_tools import answer_generate, question_understand
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

        intent_res = question_understand("报销需要哪些附件")
        self.assertTrue(intent_res.success)
        self.assertEqual(intent_res.data["intent"], "policy")

        ans_res = answer_generate("问题", [{"title": "条款A", "source": "kb", "score": 0.88}])
        self.assertTrue(ans_res.success)
        self.assertIn("条款A", ans_res.data["answer"])


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


if __name__ == "__main__":
    unittest.main()
