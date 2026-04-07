import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

# 提前 Mock trulens_eval 以避免在某些环境（如 Windows + Python 3.13）下的 import 崩溃
mock_trulens = MagicMock()
sys.modules["trulens_eval"] = mock_trulens
sys.modules["trulens_eval.feedback"] = MagicMock()
sys.modules["trulens_eval.feedback.provider"] = MagicMock()
sys.modules["trulens_eval.feedback.provider.openai"] = MagicMock()

# Add project root to sys.path
repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from agent.eval.trulens_rag import run_trulens_rag_eval

def verify():
    print("开始验证 RAG 评估流程 (已 Mock TruLens 以避免环境崩溃)...")
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        
        # 1. 创建模拟知识库
        kb_path = tmp_path / "mock_kb.json"
        kb_data = {
            "chunks": [
                {
                    "title": "办公用品领用规定",
                    "content": "员工每月可领用笔记本 2 本，签字笔 5 支。超过部分需部门主管审批。",
                    "source": "行政部"
                },
                {
                    "title": "差旅住宿标准",
                    "content": "北京、上海住宿标准为 500 元/天，其他城市 350 元/天。",
                    "source": "财务部"
                }
            ]
        }
        kb_path.write_text(json.dumps(kb_data, ensure_ascii=False), encoding="utf-8")
        
        # 2. 定义评估问题
        questions = [
            {
                "id": "q1",
                "question": "笔记本一个月可以领多少个？",
                "expected_keywords": ["2本", "笔记本"]
            },
            {
                "id": "q2",
                "question": "上海的住宿标准是多少？",
                "expected_keywords": ["500元", "上海"]
            }
        ]
        
        # 3. 运行评估
        os.environ["AGENT_TRULENS_USE_LLM_JUDGE"] = "false"
        
        try:
            # 配置 Mock 行为
            mock_tru_app = MagicMock()
            mock_tru_app.__enter__.return_value = MagicMock(record_id="mock_record_id")
            mock_trulens.TruBasicApp.return_value = mock_tru_app
            
            print(f"正在运行评估，KB 路径: {kb_path}")
            # Mock search_policy to avoid real KB search
            with MagicMock() as mock_search:
                import agent.eval.trulens_rag
                agent.eval.trulens_rag.search_policy = MagicMock(side_effect=lambda q, top_k, kb_path: [
                    MagicMock(content="员工每月可领用笔记本 2 本", source="src", title="tit", score=1.0)
                ])
                
                result = run_trulens_rag_eval(
                    kb_path=kb_path,
                    questions=questions,
                    top_k=2,
                    output_dir=tmp_path / "eval_results"
                )
            
            report_path = Path(result["report_path"])
            print(f"评估完成，报告路径: {report_path}")
            
            # 4. 验证报告内容
            if not report_path.exists():
                print("错误: 报告文件未生成")
                sys.exit(1)
                
            report = json.loads(report_path.read_text(encoding="utf-8"))
            summary = report["summary"]
            
            print("\n评估摘要:")
            print(f"- 样本数量: {summary['sample_count']}")
            print(f"- 通过率: {summary['pass_rate']:.2%}")
            print(f"- 平均上下文相关性: {summary['avg_context_relevance']:.4f}")
            print(f"- 平均答案可靠性: {summary['avg_answer_groundedness']:.4f}")
            
            assert summary["sample_count"] == 2
            assert summary["pass_count"] >= 0
            assert "top_k" in summary
            assert len(report["records"]) == 2
            
            for record in report["records"]:
                assert "is_pass" in record
                assert "scores" in record
                print(f"问题: {record['question']} -> 通过: {record['is_pass']}")

            print("\n验证成功！")
            
        except Exception as e:
            print(f"验证过程中发生错误: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

if __name__ == "__main__":
    verify()
