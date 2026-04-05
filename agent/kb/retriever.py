from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


@dataclass
class RetrievedChunk:
    source: str
    title: str
    content: str
    score: float


@dataclass
class _EmbeddingCacheEntry:
    signature: str
    texts: List[str]
    metadata: List[Dict[str, str]]
    emb_matrix: Any


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def _tokenize(text: str) -> List[str]:
    normalized = _normalize(text)
    if not normalized:
        return []

    tokens = re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", normalized)
    enriched: List[str] = []

    for token in tokens:
        if re.fullmatch(r"[\u4e00-\u9fff]", token):
            enriched.append(token)
        else:
            enriched.append(token)

    chinese_sequence = "".join(ch for ch in normalized if "\u4e00" <= ch <= "\u9fff")
    if len(chinese_sequence) >= 2:
        for idx in range(len(chinese_sequence) - 1):
            enriched.append(chinese_sequence[idx : idx + 2])

    return enriched


def _score_chunk(query: str, query_tokens: Sequence[str], chunk: Dict[str, str]) -> float:
    content = str(chunk.get("content", ""))
    haystack = _normalize(content)
    if not haystack:
        return 0.0

    overlap = 0
    for token in query_tokens:
        if token and token in haystack:
            overlap += 1

    phrase_bonus = 0.0
    query_norm = _normalize(query)
    if query_norm and query_norm in haystack:
        phrase_bonus = 2.0

    length_penalty = min(len(haystack) / 2000.0, 1.0)
    return overlap + phrase_bonus - length_penalty * 0.3


def _load_kb(kb_path: str | Path) -> Dict[str, object]:
    path = Path(kb_path)
    if not path.exists():
        raise FileNotFoundError(f"知识库文件不存在: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------
# SentenceTransformer model
# ---------------------------
_model = None
_embedding_cache: Dict[str, _EmbeddingCacheEntry] = {}
_EMBED_MODEL_NAME = "jinaai/jina-embeddings-v5-text-nano-retrieval"


def _get_model():
    global _model
    if _model is not None:
        return _model

    try:
        import torch
        from sentence_transformers import SentenceTransformer

        device = "cuda" if torch.cuda.is_available() else "cpu"
        _model = SentenceTransformer(
            _EMBED_MODEL_NAME,
            trust_remote_code=True,
            device=device,
        )
        return _model
    except Exception:
        _model = None
        return None


def _embed_texts(texts: List[str]):
    model = _get_model()
    if model is None:
        raise RuntimeError("Embedding model is not available")

    # delay import numpy to runtime
    import numpy as np

    emb = model.encode(texts, convert_to_numpy=True, show_progress_bar=False, batch_size=32)
    # ensure 2D
    return emb


def _to_hybrid_score(vector_score: float, keyword_score: float) -> float:
    keyword_component = min(max(keyword_score, 0.0), 8.0) / 8.0
    vector_component = max(vector_score, -1.0)
    return vector_component * 0.75 + keyword_component * 0.25


def _candidate_key(source: str, title: str, content: str) -> Tuple[str, str, str]:
    return (source.strip(), title.strip(), content.strip())


def _collect_keyword_candidates(
    query: str,
    query_tokens: Sequence[str],
    chunks: Sequence[Dict[str, str]],
    *,
    limit: int,
) -> List[Tuple[Dict[str, str], float]]:
    scored: List[Tuple[Dict[str, str], float]] = []
    for item in chunks:
        if not isinstance(item, dict):
            continue
        score = _score_chunk(query, query_tokens, item)
        if score <= 0:
            continue
        scored.append((item, score))
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[: max(1, limit)]


def _build_kb_signature(kb_path: Path, chunks: Sequence[Dict[str, object]]) -> str:
    try:
        st = kb_path.stat()
        return f"{kb_path.resolve()}::{st.st_mtime_ns}:{st.st_size}:{len(chunks)}"
    except OSError:
        return f"{kb_path.resolve()}::na:{len(chunks)}"


def _get_cached_embedding_index(
    kb_path: Path,
    chunks: Sequence[Dict[str, object]],
) -> Tuple[List[str], List[Dict[str, str]], Any]:
    cache_key = str(kb_path.resolve())
    signature = _build_kb_signature(kb_path, chunks)
    cached = _embedding_cache.get(cache_key)
    if cached and cached.signature == signature:
        return cached.texts, cached.metadata, cached.emb_matrix

    texts: List[str] = []
    metadata: List[Dict[str, str]] = []
    for item in chunks:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        content = str(item.get("content", "")).strip()
        source = str(item.get("source", kb_path))
        full = (title + "\n" + content).strip()
        if not full:
            continue
        texts.append(full)
        metadata.append({"title": title or "未命名片段", "content": content, "source": source})

    emb_matrix = _embed_texts(texts)
    _embedding_cache[cache_key] = _EmbeddingCacheEntry(
        signature=signature,
        texts=texts,
        metadata=metadata,
        emb_matrix=emb_matrix,
    )
    return texts, metadata, emb_matrix


def retrieve_chunks(query: str, *, kb_path: str | Path, top_k: int = 4) -> List[RetrievedChunk]:
    """原有的基于词频/规则的检索，作为回退方案。"""
    if not query.strip():
        return []

    kb_payload = _load_kb(kb_path)
    chunks = kb_payload.get("chunks", [])
    if not isinstance(chunks, list):
        return []

    query_tokens = _tokenize(query)
    scored: List[RetrievedChunk] = []

    for item in chunks:
        if not isinstance(item, dict):
            continue
        score = _score_chunk(query, query_tokens, item)
        if score <= 0:
            continue
        scored.append(
            RetrievedChunk(
                source=str(item.get("source", "未知来源")),
                title=str(item.get("title", "未命名片段")),
                content=str(item.get("content", "")).strip(),
                score=score,
            )
        )

    scored.sort(key=lambda chunk: chunk.score, reverse=True)
    return scored[: max(top_k, 1)]


def format_retrieved_context(chunks: Sequence[RetrievedChunk], *, max_chars: int = 1800) -> str:
    if not chunks:
        return ""

    lines: List[str] = []
    total = 0
    for idx, chunk in enumerate(chunks, start=1):
        snippet = chunk.content.strip()
        if not snippet:
            continue
        block = f"[{idx}] 来源: {chunk.source} | 标题: {chunk.title}\n{snippet}"
        if total + len(block) > max_chars:
            break
        lines.append(block)
        total += len(block)

    return "\n\n".join(lines)


# ---------------------------
# 对外接口：语义召回
# ---------------------------
def search_policy(query: str, top_k: int = 3, kb_path: Optional[str | Path] = None) -> List[RetrievedChunk]:
    """
    使用向量检索来返回与 query 最相关的片段。

    返回值: List[RetrievedChunk]，每个包含 source（原文件路径或来源标识）、title（制度名称）、content（片段正文）、score（相似度分数）。
    """
    if not query or not query.strip():
        return []

    if kb_path is None:
        kb_path = Path(__file__).resolve().parents[2] / "data" / "kb" / "reimbursement_kb.json"

    kb_payload = _load_kb(kb_path)
    chunks = kb_payload.get("chunks", [])
    if not isinstance(chunks, list) or len(chunks) == 0:
        return []

    query_tokens = _tokenize(query)
    candidate_limit = max(top_k * 8, 12)
    keyword_candidates = _collect_keyword_candidates(
        query,
        query_tokens,
        chunks,  # type: ignore[arg-type]
        limit=candidate_limit,
    )

    resolved_path = Path(kb_path).resolve()
    db_path = resolved_path.parent / "chroma_db"
    merged: Dict[Tuple[str, str, str], RetrievedChunk] = {}

    for item, keyword_score in keyword_candidates:
        source = str(item.get("source", "未知来源"))
        title = str(item.get("title", "未命名片段"))
        content = str(item.get("content", "")).strip()
        if not content:
            continue
        combined = _to_hybrid_score(0.0, keyword_score)
        key = _candidate_key(source, title, content)
        merged[key] = RetrievedChunk(source=source, title=title, content=content, score=combined)

    # Try using ChromaDB first
    if db_path.exists():
        try:
            import chromadb
            from chromadb.utils import embedding_functions

            class JinaEmbeddingFunction(embedding_functions.EmbeddingFunction):
                def __call__(self, input: chromadb.Documents) -> chromadb.Embeddings:
                    model = _get_model()
                    if model is None:
                        raise RuntimeError("Embedding model is not available")
                    embeddings = model.encode(input, convert_to_numpy=True, show_progress_bar=False, batch_size=32)
                    return embeddings.tolist()

            client = chromadb.PersistentClient(path=str(db_path))
            emb_fn = JinaEmbeddingFunction()
            collection = client.get_collection(name="reimbursement_kb", embedding_function=emb_fn)

            results = collection.query(query_texts=[query], n_results=candidate_limit)
            if results["documents"] and results["distances"]:
                docs = results["documents"][0]
                metas = results["metadatas"][0] if results["metadatas"] else [{}] * len(docs)
                distances = results["distances"][0]

                for doc, meta, distance in zip(docs, metas, distances):
                    source = str(meta.get("source", "未知来源"))
                    title = str(meta.get("title", "未命名片段"))
                    content = str(meta.get("content", doc)).strip()
                    if not content:
                        continue
                    vector_score = 1.0 / (1.0 + float(distance))
                    keyword_score = _score_chunk(query, query_tokens, {"content": content})
                    combined = _to_hybrid_score(vector_score, keyword_score)
                    key = _candidate_key(source, title, content)
                    current = merged.get(key)
                    if current is None or combined > current.score:
                        merged[key] = RetrievedChunk(
                            source=source,
                            title=title,
                            content=content,
                            score=combined,
                        )
            if merged:
                ranked = sorted(merged.values(), key=lambda x: x.score, reverse=True)
                return ranked[: max(1, top_k)]

        except Exception:
            # fallback to dynamic embeddings
            pass

    # Fallback to dynamic embeddings + hybrid rerank
    try:
        import numpy as np

        _, metadata, emb_matrix = _get_cached_embedding_index(resolved_path, chunks)
        query_emb = _embed_texts([query])[0]

        emb_norms = np.linalg.norm(emb_matrix, axis=1)
        q_norm = np.linalg.norm(query_emb) + 1e-10
        sims = (emb_matrix @ query_emb) / (emb_norms * q_norm + 1e-12)
        order = sorted(range(len(sims)), key=lambda i: float(sims[i]), reverse=True)

        for idx in order[: min(len(order), candidate_limit)]:
            meta = metadata[idx]
            source = str(meta.get("source", "未知来源"))
            title = str(meta.get("title", "未命名片段"))
            content = str(meta.get("content", "")).strip()
            if not content:
                continue
            vector_score = float(sims[idx])
            keyword_score = _score_chunk(query, query_tokens, {"content": content})
            combined = _to_hybrid_score(vector_score, keyword_score)
            key = _candidate_key(source, title, content)
            current = merged.get(key)
            if current is None or combined > current.score:
                merged[key] = RetrievedChunk(
                    source=source,
                    title=title,
                    content=content,
                    score=combined,
                )

        if merged:
            ranked = sorted(merged.values(), key=lambda x: x.score, reverse=True)
            return ranked[: max(1, top_k)]
        return []
    except Exception:
        # 回退到基于词汇的检索
        return retrieve_chunks(query, kb_path=kb_path, top_k=top_k)
