"""
rag.py — ChromaDB-backed retrieval-augmented generation store.

Each research session gets its own isolated collection so documents
from previous queries never contaminate new results.
"""

import uuid
import hashlib

import chromadb
from sentence_transformers import SentenceTransformer


class RAGStore:
    """Index documents and retrieve the most relevant chunks by query."""

    _encoder: SentenceTransformer | None = None  # shared across instances

    def __init__(self, session_id: str = "default"):
        self._client = chromadb.PersistentClient(path="./chroma_db")
        safe = hashlib.md5(session_id.encode()).hexdigest()[:12]
        self._collection = self._client.get_or_create_collection(f"research_{safe}")
        if RAGStore._encoder is None:
            RAGStore._encoder = SentenceTransformer("all-MiniLM-L6-v2")

    # ── write ──────────────────────────────────────────────────────────────
    def add(self, docs: list[dict]) -> None:
        """
        Each doc: {content, title, url, source, authors?, published?}
        Silently skips entries with empty content.
        """
        texts, metas, ids = [], [], []
        for d in docs:
            content = (d.get("content") or "").strip()
            if not content:
                continue
            texts.append(content)
            metas.append({
                "title":     d.get("title", ""),
                "url":       d.get("url", ""),
                "source":    d.get("source", "unknown"),
                "authors":   ", ".join(d.get("authors", [])),
                "published": d.get("published", ""),
            })
            ids.append(str(uuid.uuid4()))

        if not texts:
            return

        embeddings = RAGStore._encoder.encode(texts).tolist()
        self._collection.add(documents=texts, embeddings=embeddings,
                             metadatas=metas, ids=ids)

    # ── read ───────────────────────────────────────────────────────────────
    def retrieve(self, query: str, k: int = 5) -> list[dict]:
        total = self._collection.count()
        if total == 0:
            return []
        k = min(k, total)
        emb = RAGStore._encoder.encode([query]).tolist()
        res = self._collection.query(
            query_embeddings=emb, n_results=k,
            include=["documents", "metadatas", "distances"],
        )
        docs   = res.get("documents", [[]])[0]
        metas  = res.get("metadatas",  [[]])[0]
        scores = res.get("distances",  [[]])[0]
        return [
            {"text": d, "metadata": m, "score": round(1 - s, 4)}
            for d, m, s in zip(docs, metas, scores)
        ]
