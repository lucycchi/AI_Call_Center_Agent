"""Combined keyword and meaning-based search over the chunks, merged by reciprocal-rank fusion (R28)."""

import re
from dataclasses import dataclass
from typing import Protocol

import numpy as np
from rank_bm25 import BM25Okapi

from app.knowledge.index import Chunk

TOP_K = 5
CANDIDATES = 10


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> np.ndarray: ...


@dataclass(frozen=True)
class ScoredChunk:
    chunk: Chunk
    meaning_score: float
    keyword_score: float


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9$]+", text.lower())


def fuse(rankings: list[list[str]], k: int = 60) -> list[str]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for position, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + position)
    return sorted(scores, key=scores.get, reverse=True)


class Searcher:
    """The keyword index is rebuilt from the chunks at startup; embeddings come from the built index."""

    def __init__(self, chunks: list[Chunk], embedder: Embedder, embeddings: np.ndarray | None = None):
        self._chunks = chunks
        self._by_id = {c.chunk_id: c for c in chunks}
        self._embedder = embedder
        self._vectors = embeddings if embeddings is not None else embedder.embed([c.text for c in chunks])
        self._bm25 = BM25Okapi([tokens(c.text) for c in chunks])

    def _meaning(self, question: str) -> np.ndarray:
        query = self._embedder.embed([question])[0]
        return self._vectors @ query

    def _keyword(self, question: str) -> np.ndarray:
        return np.asarray(self._bm25.get_scores(tokens(question)))

    def search(self, question: str, mode: str = "combined", k: int = TOP_K) -> list[ScoredChunk]:
        meaning, keyword = self._meaning(question), self._keyword(question)
        by_meaning = [self._chunks[i].chunk_id for i in np.argsort(-meaning)]
        by_keyword = [self._chunks[i].chunk_id for i in np.argsort(-keyword)]
        if mode == "meaning":
            order = by_meaning
        elif mode == "keyword":
            order = by_keyword
        elif mode == "combined":
            # Reciprocal-rank fusion, but the best result of each list is always kept: chosen on the working
            # set, where plain fusion dropped meaning search's correct top answer when keyword search missed it.
            order = list(dict.fromkeys([by_meaning[0], by_keyword[0]] + fuse([by_meaning[:CANDIDATES], by_keyword[:CANDIDATES]])))
        else:
            raise ValueError(f"unknown search mode {mode!r}")
        index = {c.chunk_id: i for i, c in enumerate(self._chunks)}
        return [ScoredChunk(self._by_id[cid], float(meaning[index[cid]]), float(keyword[index[cid]])) for cid in order[:k]]

    def top_meaning_score(self, question: str) -> float:
        return float(self._meaning(question).max())
