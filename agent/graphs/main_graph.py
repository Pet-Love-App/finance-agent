from __future__ import annotations

from typing import Any, Callable, Dict

from langgraph.graph import END, START, StateGraph

from agent.graphs.intent import intent_clarify_node, intent_confirm_node, route_by_task, intent_node
from agent.graphs.contracts import describe_graph_contract
from agent.graphs.names import (
    ALL_GRAPH_NODES,
    INTENT_ROUTE_TARGETS,
    NODE_ACTIVITY_PARSE,
    NODE_BUDGET_CALCULATE,
    NODE_BUDGET_FAIL,
    NODE_BUDGET_GENERATE,
    NODE_BUDGET_START,
    NODE_CLASSIFY_FILE,
    NODE_DATA_AGGREGATE,
    NODE_DATA_CLEAN,
    NODE_EXTRACT,
    NODE_FILE_EDIT_GATEWAY,
    NODE_FILE_EDIT_START,
    NODE_FINAL_FAIL,
    NODE_FINAL_GENERATE,
    NODE_FINAL_START,
    NODE_GEN_DOC,
    NODE_GEN_MAIL,
    NODE_INTENT,
    NODE_INTENT_CLARIFY,
    NODE_INTENT_CONFIRM,
    NODE_INVOICE_EXTRACT,
    NODE_LOAD_FINAL_DATA,
    NODE_LOAD_RECORD,
    NODE_QA_FALLBACK,
    NODE_QA_START,
    NODE_QUESTION_UNDERSTAND,
    NODE_REIMBURSE_FAIL,
    NODE_REIMBURSE_START,
    NODE_RULE_CHECK,
    NODE_RULE_RETRIEVE,
    NODE_SANDBOX_EXECUTE,
    NODE_SANDBOX_START,
    NODE_SAVE_RECORD,
    NODE_SCAN_FILE,
)
from agent.graphs.spec import (
    BUDGET_LOAD_ROUTES,
    FINAL_CLEAN_ROUTES,
    FINAL_LOAD_ROUTES,
    INTENT_ROUTES,
    QA_UNDERSTAND_ROUTES,
    REIMBURSE_EXTRACT_ROUTES,
    REIMBURSE_RULE_ROUTES,
    REIMBURSE_SCAN_ROUTES,
)
from agent.graphs.state import AppState
from agent.graphs.task_registry import TASK_PROFILES
from agent.graphs.subgraphs.budget import (
    budget_calculate_node,
    budget_fail_node,
    budget_generate_node,
    budget_start_node,
    load_final_data_node,
    route_after_load_final_data,
)
from agent.graphs.subgraphs.file_edit import file_edit_gateway_node, file_edit_start_node
from agent.graphs.subgraphs.final_account import (
    aggregate_node,
    data_clean_node,
    final_fail_node,
    final_generate_node,
    final_start_node,
    load_records_node,
    route_after_data_clean,
    route_after_load_records,
)
from agent.graphs.subgraphs.qa import qa_fallback_node, qa_start_node, question_understand_node, route_after_understand, rule_retrieve_node
from agent.graphs.subgraphs.reimburse import (
    activity_parse_node,
    classify_file_node,
    extract_node,
    gen_doc_node,
    gen_mail_node,
    invoice_extract_node,
    reimburse_start_node,
    route_after_extract,
    route_after_rule_check,
    route_after_scan,
    reimburse_fail_node,
    rule_check_node,
    save_record_node,
    scan_file_node,
)
from agent.graphs.subgraphs.sandbox import sandbox_execute_node, sandbox_start_node


def _register_nodes(graph: StateGraph) -> None:
    node_specs: Dict[str, Callable[..., AppState]] = {
        NODE_INTENT: intent_node,
        NODE_INTENT_CLARIFY: intent_clarify_node,
        NODE_INTENT_CONFIRM: intent_confirm_node,
        NODE_REIMBURSE_START: reimburse_start_node,
        NODE_SCAN_FILE: scan_file_node,
        NODE_CLASSIFY_FILE: classify_file_node,
        NODE_EXTRACT: extract_node,
        NODE_INVOICE_EXTRACT: invoice_extract_node,
        NODE_ACTIVITY_PARSE: activity_parse_node,
        NODE_RULE_CHECK: rule_check_node,
        NODE_GEN_DOC: gen_doc_node,
        NODE_GEN_MAIL: gen_mail_node,
        NODE_SAVE_RECORD: save_record_node,
        NODE_REIMBURSE_FAIL: reimburse_fail_node,
        NODE_QA_START: qa_start_node,
        NODE_QUESTION_UNDERSTAND: question_understand_node,
        NODE_RULE_RETRIEVE: rule_retrieve_node,
        NODE_QA_FALLBACK: qa_fallback_node,
        NODE_FINAL_START: final_start_node,
        NODE_LOAD_RECORD: load_records_node,
        NODE_DATA_CLEAN: data_clean_node,
        NODE_DATA_AGGREGATE: aggregate_node,
        NODE_FINAL_GENERATE: final_generate_node,
        NODE_FINAL_FAIL: final_fail_node,
        NODE_BUDGET_START: budget_start_node,
        NODE_LOAD_FINAL_DATA: load_final_data_node,
        NODE_BUDGET_CALCULATE: budget_calculate_node,
        NODE_BUDGET_GENERATE: budget_generate_node,
        NODE_BUDGET_FAIL: budget_fail_node,
        NODE_SANDBOX_START: sandbox_start_node,
        NODE_SANDBOX_EXECUTE: sandbox_execute_node,
        NODE_FILE_EDIT_START: file_edit_start_node,
        NODE_FILE_EDIT_GATEWAY: file_edit_gateway_node,
    }
    for name, handler in node_specs.items():
        graph.add_node(name, handler)
    _validate_node_registry_contract(set(node_specs.keys()))


def _connect_intent_layer(graph: StateGraph) -> None:
    _validate_task_registry_contract()
    _validate_route_map(
        "intent",
        INTENT_ROUTES,
        allowed_targets=ALL_GRAPH_NODES,
        required_keys=INTENT_ROUTE_TARGETS,
    )

    graph.add_edge(START, NODE_INTENT)
    graph.add_conditional_edges(
        NODE_INTENT,
        route_by_task,
        INTENT_ROUTES,
    )
    graph.add_edge(NODE_INTENT_CLARIFY, END)
    graph.add_edge(NODE_INTENT_CONFIRM, END)


def _connect_reimburse_flow(graph: StateGraph) -> None:
    _validate_route_map("reimburse.scan", REIMBURSE_SCAN_ROUTES, allowed_targets=ALL_GRAPH_NODES)
    graph.add_edge(NODE_REIMBURSE_START, NODE_SCAN_FILE)
    graph.add_conditional_edges(
        NODE_SCAN_FILE,
        route_after_scan,
        REIMBURSE_SCAN_ROUTES,
    )
    _validate_route_map("reimburse.extract", REIMBURSE_EXTRACT_ROUTES, allowed_targets=ALL_GRAPH_NODES)
    graph.add_edge(NODE_CLASSIFY_FILE, NODE_EXTRACT)
    graph.add_conditional_edges(
        NODE_EXTRACT,
        route_after_extract,
        REIMBURSE_EXTRACT_ROUTES,
    )
    graph.add_edge(NODE_INVOICE_EXTRACT, NODE_ACTIVITY_PARSE)
    graph.add_edge(NODE_ACTIVITY_PARSE, NODE_RULE_CHECK)
    _validate_route_map("reimburse.rule_check", REIMBURSE_RULE_ROUTES, allowed_targets=ALL_GRAPH_NODES)
    graph.add_conditional_edges(
        NODE_RULE_CHECK,
        route_after_rule_check,
        REIMBURSE_RULE_ROUTES,
    )
    graph.add_edge(NODE_GEN_DOC, NODE_GEN_MAIL)
    graph.add_edge(NODE_GEN_MAIL, NODE_SAVE_RECORD)
    graph.add_edge(NODE_SAVE_RECORD, END)
    graph.add_edge(NODE_REIMBURSE_FAIL, END)


def _connect_qa_flow(graph: StateGraph) -> None:
    _validate_route_map("qa.understand", QA_UNDERSTAND_ROUTES, allowed_targets=ALL_GRAPH_NODES)
    graph.add_edge(NODE_QA_START, NODE_QUESTION_UNDERSTAND)
    graph.add_conditional_edges(
        NODE_QUESTION_UNDERSTAND,
        route_after_understand,
        QA_UNDERSTAND_ROUTES,
    )
    graph.add_edge(NODE_RULE_RETRIEVE, END)
    graph.add_edge(NODE_QA_FALLBACK, END)


def _connect_final_flow(graph: StateGraph) -> None:
    _validate_route_map("final.load_records", FINAL_LOAD_ROUTES, allowed_targets=ALL_GRAPH_NODES)
    graph.add_edge(NODE_FINAL_START, NODE_LOAD_RECORD)
    graph.add_conditional_edges(
        NODE_LOAD_RECORD,
        route_after_load_records,
        FINAL_LOAD_ROUTES,
    )
    _validate_route_map("final.data_clean", FINAL_CLEAN_ROUTES, allowed_targets=ALL_GRAPH_NODES)
    graph.add_conditional_edges(
        NODE_DATA_CLEAN,
        route_after_data_clean,
        FINAL_CLEAN_ROUTES,
    )
    graph.add_edge(NODE_DATA_AGGREGATE, NODE_FINAL_GENERATE)
    graph.add_edge(NODE_FINAL_GENERATE, END)
    graph.add_edge(NODE_FINAL_FAIL, END)


def _connect_budget_flow(graph: StateGraph) -> None:
    _validate_route_map("budget.load_final_data", BUDGET_LOAD_ROUTES, allowed_targets=ALL_GRAPH_NODES)
    graph.add_edge(NODE_BUDGET_START, NODE_LOAD_FINAL_DATA)
    graph.add_conditional_edges(
        NODE_LOAD_FINAL_DATA,
        route_after_load_final_data,
        BUDGET_LOAD_ROUTES,
    )
    graph.add_edge(NODE_BUDGET_CALCULATE, NODE_BUDGET_GENERATE)
    graph.add_edge(NODE_BUDGET_GENERATE, END)
    graph.add_edge(NODE_BUDGET_FAIL, END)


def _connect_sandbox_flow(graph: StateGraph) -> None:
    graph.add_edge(NODE_SANDBOX_START, NODE_SANDBOX_EXECUTE)
    graph.add_edge(NODE_SANDBOX_EXECUTE, END)


def _connect_file_edit_flow(graph: StateGraph) -> None:
    graph.add_edge(NODE_FILE_EDIT_START, NODE_FILE_EDIT_GATEWAY)
    graph.add_edge(NODE_FILE_EDIT_GATEWAY, END)


def _validate_node_registry_contract(registered_nodes: set[str]) -> None:
    if registered_nodes != ALL_GRAPH_NODES:
        missing = sorted(ALL_GRAPH_NODES - registered_nodes)
        extras = sorted(registered_nodes - ALL_GRAPH_NODES)
        raise ValueError(f"node registry contract mismatch, missing={missing}, extras={extras}")


def _validate_route_map(
    route_name: str,
    route_map: Dict[str, str],
    *,
    allowed_targets: set[str],
    required_keys: set[str] | None = None,
) -> None:
    route_targets = set(route_map.values())
    unknown_targets = sorted(route_targets - allowed_targets)
    if unknown_targets:
        raise ValueError(f"{route_name} has unknown targets: {unknown_targets}")
    if required_keys is not None:
        route_keys = set(route_map.keys())
        if route_keys != required_keys:
            missing = sorted(required_keys - route_keys)
            extras = sorted(route_keys - required_keys)
            raise ValueError(f"{route_name} route contract mismatch, missing={missing}, extras={extras}")


def _validate_task_registry_contract() -> None:
    start_nodes = {profile["start_node"] for profile in TASK_PROFILES.values()}
    missing_targets = sorted(start_nodes - INTENT_ROUTE_TARGETS)
    if missing_targets:
        raise ValueError(f"task registry start nodes missing from intent targets: {missing_targets}")


def build_main_graph() -> Any:
    graph = StateGraph(AppState)
    _register_nodes(graph)
    _connect_intent_layer(graph)
    _connect_reimburse_flow(graph)
    _connect_qa_flow(graph)
    _connect_final_flow(graph)
    _connect_budget_flow(graph)
    _connect_sandbox_flow(graph)
    _connect_file_edit_flow(graph)
    return graph.compile()


def describe_main_graph_contract() -> Dict[str, Any]:
    return describe_graph_contract()
