#!/usr/bin/env python3
"""
Simple test for agent.kb.retriever.search_policy
Runs a few queries against the local KB and prints formatted results.
"""
import sys
from pathlib import Path
import importlib.util

# Load agent/kb/retriever.py as a module without importing the whole package
repo_root = Path(__file__).resolve().parents[1]
module_path = repo_root / "agent" / "kb" / "retriever.py"
spec = importlib.util.spec_from_file_location("agent.kb.retriever", str(module_path))
retriever = importlib.util.module_from_spec(spec)
# Register module to sys.modules to satisfy dataclasses and relative imports
sys.modules[spec.name] = retriever
loader = spec.loader
assert loader is not None
loader.exec_module(retriever)

search_policy = retriever.search_policy
format_retrieved_context = retriever.format_retrieved_context

kb_path = repo_root / "data" / "kb" / "reimbursement_kb.json"

queries = ["高铁能坐一等座吗"]

any_nonempty = False
for q in queries:
    results = search_policy(q, top_k=3, kb_path=kb_path)
    print("QUERY:", q)
    print(format_retrieved_context(results))
    print("-" * 60)
    if results:
        any_nonempty = True

if not any_nonempty:
    print("TEST FAILED: no results returned for any query")
    raise SystemExit(2)

print("TEST PASSED")
