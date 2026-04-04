# agent/parser/__init__.py
from agent.parser.main import parse_knowledge_base, parse_single_file
from agent.parser.router import FileRouter

__all__ = ["parse_knowledge_base", "parse_single_file", "FileRouter"]