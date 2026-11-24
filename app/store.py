from __future__ import annotations

import re
import uuid

from rank_bm25 import BM25Okapi

from .config import get_settings
from .models import Chunk, Retrieved

NAMESPACE = uuid.UUID("6f1b1d2e-0c3a-4f9b-9a7d-2f0c1b7e5a10")
_WORD = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def chunk_text(text: str, source: str, doc_id: str, page: int | None = None,
               target: int = 1100, overlap: int = 180) -> list[Chunk]:
    """Paragraph-aware chunking with overlap.

    Splits on blank lines first so a chunk rarely straddles two clauses, then
    packs paragraphs up to `target` characters. Long paragraphs are hard-split.
    Overlap carries the tail of the previous chunk so a rule split across a
    boundary is still retrievable.
    """
    text = re.sub(r"[ \t]+", " ", text).strip()
    if not text:
        return []

    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    pieces: list[str] = []
    for p in paras:
        if len(p) <= target:
            pieces.append(p)
        else:
            for i in range(0, len(p), target):
                pieces.append(p[i : i + target])

    chunks: list[str] = []
    buf = ""
    for p in pieces:
        if buf and len(buf) + 1 + len(p) > target:
            chunks.append(buf)
            buf = (buf[-overlap:] + "\n" + p) if overlap else p
        else:
            buf = f"{buf}\n{p}" if buf else p
    if buf:
        chunks.append(buf)

    out = []
    for i, c in enumerate(chunks):
        cid = str(uuid.uuid5(NAMESPACE, f"{doc_id}:{page}:{i}:{c[:64]}"))
        out.append(Chunk(chunk_id=cid, doc_id=doc_id, source=source, page=page, text=c.strip()))
    return out


def rrf(dense_ids: list[str], bm25_ids: list[str], k: int = 60) -> dict[str, float]:
    """Reciprocal Rank Fusion.

    score(d) = sum over rankings of 1 / (k + rank(d)), rank starting at 1.
    Rank-based, so it needs no score normalisation between a cosine similarity
    and a BM25 score, which are not on comparable scales.
    """
    scores: dict[str, float] = {}
    for ranking in (dense_ids, bm25_ids):
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return scores


class HybridStore:
    """Qdrant for dense vectors, in-process BM25 for lexical, fused with RRF.

    Lexical matters here: scheme documents are full of exact tokens a dense
    model blurs — "SC/ST", "₹6,000", "Section 4(2)", "APL/BPL". Dense-only
    retrieval misses those; BM25-only misses paraphrase. Both, fused.
    """

    def __init__(self, llm, client=None) -> None:
        self.s = get_settings()
        self.llm = llm
        self._client = client
        self._bm25: BM25Okapi | None = None
        self._bm25_ids: list[str] = []
        self._cache: dict[str, Chunk] = {}

    @property
    def client(self):
        if self._client is None:
            from qdrant_client import QdrantClient

            self._client = QdrantClient(
                url=self.s.qdrant_url, api_key=self.s.qdrant_api_key or None
            )
        return self._client

    def ensure_collection(self) -> None:
        from qdrant_client.models import Distance, VectorParams

        existing = {c.name for c in self.client.get_collections().collections}
        if self.s.collection not in existing:
            self.client.create_collection(
                collection_name=self.s.collection,
                vectors_config=VectorParams(size=self.s.embed_dim, distance=Distance.COSINE),
            )

    def upsert(self, chunks: list[Chunk], batch: int = 64) -> int:
        from qdrant_client.models import PointStruct

        self.ensure_collection()
        total = 0
        for i in range(0, len(chunks), batch):
            part = chunks[i : i + batch]
            vecs = self.llm.embed([c.text for c in part], dim=self.s.embed_dim)
            self.client.upsert(
                collection_name=self.s.collection,
                points=[
                    PointStruct(id=c.chunk_id, vector=v, payload=c.model_dump())
                    for c, v in zip(part, vecs)
                ],
            )
            total += len(part)
        return total

    def load_lexical_index(self) -> int:
        """Pull every chunk's text out of Qdrant to build the BM25 index.

        Fine at this corpus size (thousands of chunks). Documented as the first
        thing to replace if the corpus grows: move to Qdrant's own sparse
        vectors or an external search index.
        """
        chunks: list[Chunk] = []
        offset = None
        while True:
            points, offset = self.client.scroll(
                collection_name=self.s.collection, limit=512, offset=offset, with_payload=True
            )
            chunks.extend(Chunk(**p.payload) for p in points)
            if offset is None:
                break
        self._cache = {c.chunk_id: c for c in chunks}
        self._bm25_ids = [c.chunk_id for c in chunks]
        self._bm25 = BM25Okapi([tokenize(c.text) for c in chunks]) if chunks else None
        return len(chunks)

    def search(self, query: str, top_k: int | None = None) -> list[Retrieved]:
        top_k = top_k or self.s.top_k
        if self._bm25 is None:
            self.load_lexical_index()

        qvec = self.llm.embed([query], dim=self.s.embed_dim, task="RETRIEVAL_QUERY")[0]
        hits = self.client.query_points(
            collection_name=self.s.collection, query=qvec, limit=top_k * 2, with_payload=True
        ).points
        dense_ids = []
        for h in hits:
            c = Chunk(**h.payload)
            self._cache[c.chunk_id] = c
            dense_ids.append(c.chunk_id)

        bm25_ids: list[str] = []
        if self._bm25 is not None and self._bm25_ids:
            scores = self._bm25.get_scores(tokenize(query))
            order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
            bm25_ids = [self._bm25_ids[i] for i in order[: top_k * 2] if scores[i] > 0]

        fused = rrf(dense_ids, bm25_ids, k=self.s.rrf_k)
        ranked = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)[:top_k]

        out = []
        for cid, score in ranked:
            chunk = self._cache.get(cid)
            if chunk is None:
                continue
            out.append(
                Retrieved(
                    chunk=chunk,
                    dense_rank=dense_ids.index(cid) + 1 if cid in dense_ids else None,
                    bm25_rank=bm25_ids.index(cid) + 1 if cid in bm25_ids else None,
                    fused_score=round(score, 6),
                )
            )
        return out


class InMemoryStore(HybridStore):
    """Same interface, no Qdrant. Used by the offline test suite."""

    def __init__(self, llm, chunks: list[Chunk]) -> None:
        self.s = get_settings()
        self.llm = llm
        self._cache = {c.chunk_id: c for c in chunks}
        self._chunks = chunks
        self._vectors = llm.embed([c.text for c in chunks], dim=self.s.embed_dim) if chunks else []
        self._bm25_ids = [c.chunk_id for c in chunks]
        self._bm25 = BM25Okapi([tokenize(c.text) for c in chunks]) if chunks else None

    def ensure_collection(self) -> None:  # pragma: no cover
        return

    def load_lexical_index(self) -> int:
        return len(self._chunks)

    def search(self, query: str, top_k: int | None = None) -> list[Retrieved]:
        top_k = top_k or self.s.top_k
        if not self._chunks:
            return []
        qvec = self.llm.embed([query], dim=self.s.embed_dim, task="RETRIEVAL_QUERY")[0]
        sims = [sum(a * b for a, b in zip(qvec, v)) for v in self._vectors]
        order = sorted(range(len(sims)), key=lambda i: sims[i], reverse=True)
        dense_ids = [self._chunks[i].chunk_id for i in order[: top_k * 2]]

        scores = self._bm25.get_scores(tokenize(query))
        border = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        bm25_ids = [self._bm25_ids[i] for i in border[: top_k * 2] if scores[i] > 0]

        fused = rrf(dense_ids, bm25_ids, k=self.s.rrf_k)
        ranked = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
        return [
            Retrieved(
                chunk=self._cache[cid],
                dense_rank=dense_ids.index(cid) + 1 if cid in dense_ids else None,
                bm25_rank=bm25_ids.index(cid) + 1 if cid in bm25_ids else None,
                fused_score=round(sc, 6),
            )
            for cid, sc in ranked
        ]
