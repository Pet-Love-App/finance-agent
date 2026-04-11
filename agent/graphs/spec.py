from __future__ import annotations

from typing import Any, Dict

from agent.graphs.names import (
    INTENT_ROUTE_TARGETS,
    NODE_ACTIVITY_PARSE,
    NODE_BUDGET_CALCULATE,
    NODE_BUDGET_FAIL,
    NODE_BUDGET_GENERATE,
    NODE_CLASSIFY_FILE,
    NODE_COLLECT_INFO,
    NODE_DATA_AGGREGATE,
    NODE_DATA_CLEAN,
    NODE_FINAL_FAIL,
    NODE_FINAL_GENERATE,
    NODE_GEN_DOC,
    NODE_INVOICE_EXTRACT,
    NODE_QA_FALLBACK,
    NODE_REIMBURSE_FAIL,
    NODE_RULE_RETRIEVE,
    NODE_SAVE_RECORD,
)

INTENT_ROUTES: Dict[str, str] = {target: target for target in sorted(INTENT_ROUTE_TARGETS)}

REIMBURSE_SCAN_ROUTES: Dict[str, str] = {
    NODE_CLASSIFY_FILE: NODE_CLASSIFY_FILE,
    NODE_SAVE_RECORD: NODE_SAVE_RECORD,
    NODE_REIMBURSE_FAIL: NODE_REIMBURSE_FAIL,
}

REIMBURSE_EXTRACT_ROUTES: Dict[str, str] = {
    NODE_INVOICE_EXTRACT: NODE_INVOICE_EXTRACT,
    NODE_ACTIVITY_PARSE: NODE_ACTIVITY_PARSE,
    NODE_REIMBURSE_FAIL: NODE_REIMBURSE_FAIL,
}

REIMBURSE_RULE_ROUTES: Dict[str, str] = {
    NODE_COLLECT_INFO: NODE_COLLECT_INFO,
    NODE_SAVE_RECORD: NODE_SAVE_RECORD,
}

QA_UNDERSTAND_ROUTES: Dict[str, str] = {
    NODE_RULE_RETRIEVE: NODE_RULE_RETRIEVE,
    NODE_QA_FALLBACK: NODE_QA_FALLBACK,
}

FINAL_LOAD_ROUTES: Dict[str, str] = {
    NODE_DATA_CLEAN: NODE_DATA_CLEAN,
    NODE_FINAL_GENERATE: NODE_FINAL_GENERATE,
    NODE_FINAL_FAIL: NODE_FINAL_FAIL,
}

FINAL_CLEAN_ROUTES: Dict[str, str] = {
    NODE_DATA_AGGREGATE: NODE_DATA_AGGREGATE,
    NODE_FINAL_GENERATE: NODE_FINAL_GENERATE,
    NODE_FINAL_FAIL: NODE_FINAL_FAIL,
}

BUDGET_LOAD_ROUTES: Dict[str, str] = {
    NODE_BUDGET_CALCULATE: NODE_BUDGET_CALCULATE,
    NODE_BUDGET_GENERATE: NODE_BUDGET_GENERATE,
    NODE_BUDGET_FAIL: NODE_BUDGET_FAIL,
}

CONDITIONAL_ROUTE_SPECS: Dict[str, Dict[str, str]] = {
    "intent": INTENT_ROUTES,
    "reimburse.scan": REIMBURSE_SCAN_ROUTES,
    "reimburse.extract": REIMBURSE_EXTRACT_ROUTES,
    "reimburse.rule_check": REIMBURSE_RULE_ROUTES,
    "qa.understand": QA_UNDERSTAND_ROUTES,
    "final.load_records": FINAL_LOAD_ROUTES,
    "final.data_clean": FINAL_CLEAN_ROUTES,
    "budget.load_final_data": BUDGET_LOAD_ROUTES,
}


def build_conditional_route_snapshot() -> Dict[str, Any]:
    return {
        name: {
            "keys": sorted(route_map.keys()),
            "targets": sorted(set(route_map.values())),
        }
        for name, route_map in sorted(CONDITIONAL_ROUTE_SPECS.items())
    }

