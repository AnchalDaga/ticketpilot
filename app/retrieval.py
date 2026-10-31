import re
from functools import lru_cache
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

KB_DIR = Path(__file__).resolve().parent.parent / "kb"
MODEL_NAME = "all-MiniLM-L6-v2"
RRF_K = 60


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


@lru_cache(maxsize=1)
def _index():
    docs = []
    for path in sorted(KB_DIR.glob("KB-*.md")):
        text = path.read_text()
        first_line = text.splitlines()[0].lstrip("# ")
        doc_id, title = first_line.split(": ", 1)
        docs.append({"id": doc_id, "title": title, "text": text})
    if not docs:
        raise RuntimeError("No KB files found. Run: python -m scripts.make_kb")
    bm25 = BM25Okapi([_tokenize(d["text"]) for d in docs])
    model = SentenceTransformer(MODEL_NAME)
    vecs = np.asarray(model.encode([d["text"] for d in docs], normalize_embeddings=True))
    return docs, bm25, model, vecs


def _rank_bm25(query: str) -> list[int]:
    _, bm25, _, _ = _index()
    scores = bm25.get_scores(_tokenize(query))
    return [int(i) for i in np.argsort(-scores)]


def _rank_embed(query: str) -> list[int]:
    _, _, model, vecs = _index()
    q = model.encode([query], normalize_embeddings=True)[0]
    return [int(i) for i in np.argsort(-(vecs @ q))]


def search(query: str, k: int = 3, mode: str = "hybrid") -> list[dict]:
    docs = _index()[0]
    if mode == "bm25":
        order = _rank_bm25(query)
    elif mode == "embed":
        order = _rank_embed(query)
    elif mode == "hybrid":
        fused: dict[int, float] = {}
        for ranking in (_rank_bm25(query), _rank_embed(query)):
            for rank, idx in enumerate(ranking):
                fused[idx] = fused.get(idx, 0.0) + 1.0 / (RRF_K + rank + 1)
        order = sorted(fused, key=fused.get, reverse=True)
    else:
        raise ValueError("mode must be 'bm25', 'embed', or 'hybrid'")
    return [
        {"id": docs[i]["id"], "title": docs[i]["title"], "text": docs[i]["text"]}
        for i in order[:k]
    ]