from __future__ import annotations

from agent.graphs.policy import get_bool_policy, get_int_policy, get_policy_value
from agent.graphs.state import AppState
from agent.tools import answer_generate, question_understand, rag_retrieve, rule_retrieve


def qa_start_node(state: AppState) -> AppState:
    return {"task_progress": state.get("task_progress", []) + [{"step": "qa_start", "tool_name": "start"}]}


def route_after_understand(state: AppState) -> str:
    payload = state.get("payload", {})
    query = str(state.get("payload", {}).get("normalized_query", "")).strip()
    allow_empty_query = get_bool_policy(payload, "qa_allow_empty_query", False)
    if query or allow_empty_query:
        return "RuleRetrieveNode"
    return "QAFallbackNode"


def question_understand_node(state: AppState) -> AppState:
    query = str(state.get("payload", {}).get("query", ""))
    res = question_understand(query)
    normalized_query = res.data.get("question", query) if res.success else query
    return {
        "task_progress": state.get("task_progress", []) + [{"step": "qa_understand", "tool_name": "question_understand"}],
        "payload": {**state.get("payload", {}), "normalized_query": normalized_query},
        "errors": state.get("errors", []) + ([res.error] if res.error else []),
    }


def qa_fallback_node(state: AppState) -> AppState:
    answer = "未识别到有效问题，请补充报销场景、票据类型和金额区间后再提问。"
    errors = state.get("errors", []) + ["问题为空或无法解析"]
    return {
        "qa_answer": {"answer": answer, "citations": []},
        "result": {"type": "qa", "answer": answer, "citations": [], "retrieval": "fallback", "items_count": 0, "errors": errors},
        "errors": errors,
        "task_progress": state.get("task_progress", []) + [{"step": "qa_fallback", "tool_name": "fallback"}],
    }


def rule_retrieve_node(state: AppState) -> AppState:
    query = str(state.get("payload", {}).get("normalized_query", ""))
    payload = state.get("payload", {})
    simple_res = rule_retrieve(query, payload.get("rules_path"))
    items = simple_res.data.get("items", [])
    retrieval = "rule_retrieve"
    if not items:
        top_k = get_int_policy(payload, "qa_kb_top_k", 4, legacy_keys=("kb_top_k",))
        score_threshold = get_policy_value(payload, "qa_kb_score_threshold", None, legacy_keys=("kb_score_threshold",))
        rag_res = rag_retrieve(
            query,
            payload.get("kb_path"),
            top_k=top_k,
            score_threshold=score_threshold,
        )
        items = rag_res.data.get("items", [])
        retrieval = rag_res.data.get("retrieval", "rag_retrieve")
    answer_res = answer_generate(query, items)
    errors = list(state.get("errors", []))
    if simple_res.error:
        errors.append(simple_res.error)
    if not items and "rag_res" in locals() and rag_res.error:
        errors.append(rag_res.error)
    if answer_res.error:
        errors.append(answer_res.error)
    return {
        "qa_answer": {
            "answer": answer_res.data.get("answer", ""),
            "citations": answer_res.data.get("citations", []),
        },
        "result": {
            "type": "qa",
            "answer": answer_res.data.get("answer", ""),
            "citations": answer_res.data.get("citations", []),
            "retrieval": retrieval,
            "items_count": len(items),
            "errors": errors,
        },
        "errors": errors,
        "task_progress": state.get("task_progress", []) + [{"step": "qa_retrieve", "tool_name": "rule_retrieve/rag_retrieve/answer_generate"}],
    }
