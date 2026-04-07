from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# 提前 Mock trulens_eval 以避免在某些环境下的 import 崩溃
mock_trulens = MagicMock()
sys.modules["trulens_eval"] = mock_trulens
sys.modules["trulens_eval.feedback"] = MagicMock()
sys.modules["trulens_eval.feedback.provider"] = MagicMock()
sys.modules["trulens_eval.feedback.provider.openai"] = MagicMock()

repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from agent.eval.trulens_rag import (  # noqa: E402
    _expected_keyword_hit_score,
    build_eval_questions_from_kb,
    load_eval_questions,
    run_trulens_rag_eval,
)


class TestTruLensEvalHelpers(unittest.TestCase):
    def test_build_eval_questions_from_kb(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            kb_path = Path(tmp) / "kb.json"
            kb_path.write_text(
                json.dumps(
                    {
                        "chunks": [
                            {"title": "差旅报销条款", "content": "内容A"},
                            {"title": "发票要求", "content": "内容B"},
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            samples = build_eval_questions_from_kb(kb_path, max_samples=2)
            self.assertEqual(len(samples), 2)
            self.assertIn("差旅报销条款", samples[0]["question"])

    def test_load_eval_questions_with_dict_samples(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dataset_path = Path(tmp) / "samples.json"
            dataset_path.write_text(
                json.dumps(
                    {
                        "samples": [
                            {
                                "id": "q1",
                                "question": "高铁一等座可以报销吗？",
                                "expected_keywords": ["高铁", "报销"],
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            rows = load_eval_questions(dataset_path)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["id"], "q1")
            self.assertEqual(rows[0]["expected_keywords"], ["高铁", "报销"])

    def test_expected_keyword_hit_score(self) -> None:
        payload = {
            "answer": "高铁一等座在符合标准时可报销",
            "contexts": ["差旅报销规则说明"],
        }
        score = _expected_keyword_hit_score(["高铁", "报销", "住宿"], payload)
        self.assertAlmostEqual(score, 2.0 / 3.0, places=6)

    def test_run_eval_requires_valid_top_k(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            kb_path = Path(tmp) / "kb.json"
            kb_path.write_text(json.dumps({"chunks": [{"title": "条款", "content": "内容"}]}, ensure_ascii=False), encoding="utf-8")
            
            # 确保 Mock trulens_eval 包含 TruBasicApp
            with patch("trulens_eval.TruBasicApp", MagicMock()):
                with self.assertRaises(ValueError):
                    run_trulens_rag_eval(
                        kb_path=kb_path,
                        questions=[{"id": "q1", "question": "报销规则？"}],
                        top_k=0,
                        output_dir=tmp,
                    )

    def test_run_eval_success_mocked(self) -> None:
        """测试 run_trulens_rag_eval 的主流程（Mock TruLens）"""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            kb_path = tmp_path / "kb.json"
            kb_data = {"chunks": [{"title": "核心内容", "content": "这里有核心内容供测试"}]}
            kb_path.write_text(json.dumps(kb_data, ensure_ascii=False), encoding="utf-8")
            
            # Mock TruLens components
            mock_tru_app = MagicMock()
            mock_tru_app.__enter__.return_value = MagicMock(record_id="test_record_123")
            
            with patch("trulens_eval.TruBasicApp", return_value=mock_tru_app):
                with patch("agent.eval.trulens_rag.search_policy") as mock_search:
                    # 确保返回的内容包含 question 中的词和 expected_keywords
                    mock_search.return_value = [
                        MagicMock(content="这里有 核心内容 供测试", source="src", title="核心内容", score=1.0)
                    ]
                    
                    result = run_trulens_rag_eval(
                        kb_path=kb_path,
                        questions=[{"id": "q1", "question": "什么是 核心内容 ？", "expected_keywords": ["核心内容"]}],
                        top_k=1,
                        output_dir=tmp_path / "/out",
                    )
                    
                    self.assertIn("report_path", result)
                    self.assertEqual(result["summary"]["sample_count"], 1)
                    # 现在平均分应该是 (1+1+1)/3 = 1.0 >= 0.7
                    self.assertEqual(result["summary"]["pass_count"], 1)
                    self.assertEqual(result["summary"]["pass_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
