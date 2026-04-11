from agent.kb.retriever import _embed_texts
import numpy as np
import sys

def semantic_similarity(text1, text2):
    try:
        if not text1 or not text2:
            return 0.0
        embs = _embed_texts([text1, text2])
        v1, v2 = embs[0], embs[1]
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return float(np.dot(v1, v2) / (norm1 * norm2))
    except Exception as e:
        return 0.0

if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(1)
    print(semantic_similarity(sys.argv[1], sys.argv[2]))
