"""
agent/parser/utils/hash_utils.py
"""
import hashlib
from pathlib import Path


def file_sha1(file_path: str, prefix: str = "") -> str:
    """返回 <prefix>__<stem>__sha1<8位>，作为 doc_id"""
    h = hashlib.sha1(Path(file_path).read_bytes()).hexdigest()[:8]
    stem = Path(file_path).stem
    parts = [p for p in [prefix, stem, f"sha1{h}"] if p]
    return "__".join(parts)