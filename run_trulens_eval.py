from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from agent.eval import build_eval_questions_from_kb, load_eval_questions, run_trulens_rag_eval


def main() -> None:
    parser = argparse.ArgumentParser(description="运行 TruLens RAG 评估")
    parser.add_argument("--kb-path", default="data/kb/reimbursement_kb.json", help="知识库 JSON 路径")
    parser.add_argument("--dataset", default="", help="评估问题集 JSON 路径（可选）")
    parser.add_argument("--top-k", type=int, default=4, help="检索 Top-K")
    parser.add_argument("--max-samples", type=int, default=30, help="未提供数据集时，从 KB 自动抽样数量")
    parser.add_argument("--app-id", default="agent_rag_eval", help="TruLens app_id")
    parser.add_argument("--output-dir", default="data/eval", help="评估结果输出目录")
    parser.add_argument("--use-llm-judge", action="store_true", help="启用 TruLens OpenAI Judge（需配置 AGENT_LLM_API_KEY）")
    parser.add_argument("--judge-model", default="gpt-4o-mini", help="LLM Judge 模型名")
    parser.add_argument("--pass-threshold", type=float, default=0.7, help="评估通过阈值 (0.0-1.0)")
    args = parser.parse_args()

    kb_path = Path(args.kb_path).resolve()
    if not kb_path.exists():
        raise FileNotFoundError(f"知识库不存在: {kb_path}")

    if args.dataset:
        dataset_path = Path(args.dataset).resolve()
        if not dataset_path.exists():
            raise FileNotFoundError(f"评估数据集不存在: {dataset_path}")
        questions = load_eval_questions(dataset_path)
    else:
        questions = build_eval_questions_from_kb(kb_path, max_samples=max(1, args.max_samples))

    if not questions:
        raise RuntimeError("评估问题集为空，无法执行评估")

    if args.use_llm_judge:
        os.environ["AGENT_TRULENS_USE_LLM_JUDGE"] = "true"
        os.environ["AGENT_TRULENS_JUDGE_MODEL"] = args.judge_model
    
    os.environ["AGENT_TRULENS_PASS_THRESHOLD"] = str(args.pass_threshold)

    result = run_trulens_rag_eval(
        kb_path=kb_path,
        questions=questions,
        top_k=max(1, args.top_k),
        app_id=args.app_id,
        output_dir=args.output_dir,
    )
    print(json.dumps({"ok": True, **result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
