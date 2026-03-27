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

_TOKEN_RE = re.compile(r"[a-zA-Z0-9_\-]+|[\u4e00-\u9fff]+")


def _tokenise(text: str) -> List[str]:
    """Lowercase tokenisation with extra n-grams for CJK recall robustness."""
    tokens: List[str] = []
    for raw_token in _TOKEN_RE.findall(text):
        token = raw_token.lower()
        tokens.append(token)
        if re.fullmatch(r"[\u4e00-\u9fff]+", raw_token) and len(raw_token) > 2:
            for size in (2, 3, 4):
                if len(raw_token) <= size:
                    continue
                for idx in range(len(raw_token) - size + 1):
                    tokens.append(raw_token[idx:idx + size].lower())
    return tokens


def _entry_text(entry: MemoryEntry) -> str:
    """Combine searchable fields of a MemoryEntry into one string."""
    fact_parts: List[str] = []
    for key, values in entry.facts.items():
        fact_parts.append(key)
        fact_parts.extend(values)

    parts = [
        entry.topic,
        entry.rubric,
        " ".join(entry.tags),
        " ".join(entry.keywords),
        " ".join(entry.concepts),
        " ".join(fact_parts),
        " ".join(fact_parts),
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
        boosted_scores = self._apply_field_boosts(query, q_tokens, scores)

        # Fallback: if best TF-IDF score is 0 use keyword overlap
        if max(boosted_scores) == 0.0:
            boosted_scores = self._keyword_scores(q_tokens)

        ranked: List[Tuple[float, int]] = sorted(
            ((s, i) for i, s in enumerate(boosted_scores)),
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

    def _apply_field_boosts(self, query: str, q_tokens: List[str], base_scores: List[float]) -> List[float]:
        """Boost matches in high-signal fields so recall favors concrete project facts over generic chat memory."""
        query_lower = query.lower()
        q_set = set(q_tokens)
        boosted: List[float] = []

        for index, entry in enumerate(self._entries):
            score = base_scores[index]

            topic_tokens = set(_tokenise(entry.topic))
            keyword_tokens = set(_tokenise(" ".join(entry.keywords)))
            tag_tokens = set(_tokenise(" ".join(entry.tags)))
            concept_tokens = set(_tokenise(" ".join(entry.concepts)))

            score += len(q_set & topic_tokens) * 4.0
            score += len(q_set & keyword_tokens) * 3.0
            score += len(q_set & tag_tokens) * 2.0
            score += len(q_set & concept_tokens) * 1.5

            topic_lower = entry.topic.lower()
            if query_lower and query_lower in topic_lower:
                score += 8.0

            for phrase in [entry.topic, *entry.keywords[:4]]:
                phrase_lower = phrase.lower().strip()
                if phrase_lower and phrase_lower in query_lower:
                    score += 5.0

            boosted.append(score)

        return boosted
