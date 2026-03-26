"""TF-IDF retriever with keyword fallback for memory search."""

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from typing import Dict, List, Tuple

from .models import MemoryEntry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tokeniser
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[a-zA-Z0-9\u4e00-\u9fff]+")


def _tokenise(text: str) -> List[str]:
    """Lowercase tokenisation; keeps CJK characters as single tokens."""
    return [tok.lower() for tok in _TOKEN_RE.findall(text)]


def _entry_text(entry: MemoryEntry) -> str:
    """Combine searchable fields of a MemoryEntry into one string."""
    parts = [
        entry.topic,
        entry.rubric,
        " ".join(entry.tags),
        " ".join(entry.keywords),
        " ".join(entry.concepts),
        " ".join(entry.transcript_highlights),
    ]
    return " ".join(parts)


# ---------------------------------------------------------------------------
# TF-IDF Retriever
# ---------------------------------------------------------------------------


class TFIDFRetriever:
    """Simple TF-IDF retriever over a list of MemoryEntry objects.

    Falls back to keyword overlap when the corpus is tiny or TF-IDF
    produces no meaningful scores.
    """

    def __init__(self, entries: List[MemoryEntry]) -> None:
        self._entries = entries
        self._docs: List[List[str]] = []
        self._idf: Dict[str, float] = {}
        self._build_index()

    # -- index ---------------------------------------------------------------

    def _build_index(self) -> None:
        """Tokenise documents and compute IDF."""
        n = len(self._entries)
        if n == 0:
            return

        self._docs = [_tokenise(_entry_text(e)) for e in self._entries]

        # Document frequency
        df: Dict[str, int] = {}
        for tokens in self._docs:
            for tok in set(tokens):
                df[tok] = df.get(tok, 0) + 1

        # IDF with smoothing
        self._idf = {tok: math.log((n + 1) / (freq + 1)) + 1 for tok, freq in df.items()}

    # -- search --------------------------------------------------------------

    def search(self, query: str, top_k: int = 5) -> List[MemoryEntry]:
        """Return the top-k most relevant entries for *query*."""
        if not self._entries:
            return []

        q_tokens = _tokenise(query)
        if not q_tokens:
            return []

        scores = self._tfidf_scores(q_tokens)

        # Fallback: if best TF-IDF score is 0 use keyword overlap
        if max(scores) == 0.0:
            scores = self._keyword_scores(q_tokens)

        ranked: List[Tuple[float, int]] = sorted(
            ((s, i) for i, s in enumerate(scores)),
            key=lambda x: x[0],
            reverse=True,
        )

        results: List[MemoryEntry] = []
        for score, idx in ranked[:top_k]:
            if score > 0.0:
                results.append(self._entries[idx])
        return results

    def _tfidf_scores(self, q_tokens: List[str]) -> List[float]:
        """Compute TF-IDF cosine-ish scores for each document."""
        q_counter = Counter(q_tokens)
        scores: List[float] = []
        for doc_tokens in self._docs:
            doc_counter = Counter(doc_tokens)
            score = 0.0
            for tok, q_tf in q_counter.items():
                if tok in doc_counter:
                    idf = self._idf.get(tok, 1.0)
                    score += (q_tf * idf) * (doc_counter[tok] * idf)
            scores.append(score)
        return scores

    def _keyword_scores(self, q_tokens: List[str]) -> List[float]:
        """Simple keyword-overlap fallback."""
        q_set = set(q_tokens)
        scores: List[float] = []
        for doc_tokens in self._docs:
            overlap = len(q_set & set(doc_tokens))
            scores.append(float(overlap))
        return scores
