from __future__ import annotations

from agent.graphs.state import AppState
from agent.tools import answer_generate, question_understand, rag_retrieve, rule_retrieve


def qa_start_node(state: AppState) -> AppState:
    return {"task_progress": state.get("task_progress", []) + [{"step": "qa_start", "tool_name": "start"}]}


def question_understand_node(state: AppState) -> AppState:
    query = str(state.get("payload", {}).get("query", ""))
    res = question_understand(query)
    return {
        "task_progress": state.get("task_progress", []) + [{"step": "qa_understand", "tool_name": "question_understand"}],
        "payload": {**state.get("payload", {}), "normalized_query": res.data.get("question", query)},
    }


def rule_retrieve_node(state: AppState) -> AppState:
    query = str(state.get("payload", {}).get("normalized_query", ""))
    simple_res = rule_retrieve(query, state.get("payload", {}).get("rules_path"))
    items = simple_res.data.get("items", [])
    if not items:
        rag_res = rag_retrieve(query, state.get("payload", {}).get("kb_path"), top_k=4)
        items = rag_res.data.get("items", [])
    answer_res = answer_generate(query, items)
    return {
        "qa_answer": {
            "answer": answer_res.data.get("answer", ""),
            "citations": answer_res.data.get("citations", []),
        },
        "result": {"type": "qa", "answer": answer_res.data.get("answer", ""), "citations": answer_res.data.get("citations", [])},
        "task_progress": state.get("task_progress", []) + [{"step": "qa_retrieve", "tool_name": "rule_retrieve/rag_retrieve/answer_generate"}],
    }
