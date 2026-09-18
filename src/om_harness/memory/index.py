"""In-memory inverted keyword index for fast, deterministic memory retrieval.

The index is built from a ``MemoryStore`` and kept in sync via ``add`` and
``persist``. Retrieval uses TF-IDF-like scoring with recency, access-frequency,
and confidence boosts — no embeddings, no external dependencies.

This aligns with the project's design philosophy (design.md Tradeoff 2:
"Mechanical minimization is deterministic, testable, and free").
"""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime

from om_harness.memory.models import MemoryEntry, MemoryQuery
from om_harness.memory.store import MemoryStore

# Minimum token length to index (single-character tokens are noise).
_MIN_TOKEN_LEN = 2
# Scoring weight for a tag match (tags are more selective than content terms).
_TAG_MATCH_WEIGHT = 5.0
# Recency decay: score is divided by (1 + age_days * 0.1), so a 10-day-old
# fact gets ~half the recency boost of a fresh one.
_RECENCY_DECAY = 0.1
# Access boost: each prior access adds 10% to the score.
_ACCESS_BOOST_PER_HIT = 0.1

_TOKEN_RE = re.compile(r"\b\w+\b")


def tokenize(text: str) -> list[str]:
    """Split text into lowercased tokens (words), filtering short tokens."""
    return [t for t in (w.lower() for w in _TOKEN_RE.findall(text)) if len(t) >= _MIN_TOKEN_LEN]


class MemoryIndex:
    """Inverted keyword index over memory entries, backed by a ``MemoryStore``."""

    def __init__(self, store: MemoryStore) -> None:
        self._store = store
        self._entries: dict[str, MemoryEntry] = {}
        self._term_index: dict[str, set[str]] = {}

    @property
    def store(self) -> MemoryStore:
        """The backing store (exposed for tests and index rebuilding)."""
        return self._store

    @property
    def total_entries(self) -> int:
        """Number of entries currently in the index."""
        return len(self._entries)

    def clear(self) -> None:
        """Clear all entries from the in-memory index (does not touch the store)."""
        self._entries.clear()
        self._term_index.clear()

    # -- building / syncing ----------------------------------------------------

    def build(self) -> None:
        """Load all entries from the store and rebuild the in-memory index."""
        entries = self._store.load_all()
        self._entries = {e.entry_id: e for e in entries}
        self._term_index = {}
        for entry in entries:
            self._index_entry(entry)

    def _index_entry(self, entry: MemoryEntry) -> None:
        """Index an entry's content and tags (does not persist to store)."""
        terms = tokenize(entry.content) + [t.lower() for t in entry.tags]
        for term in set(terms):
            self._term_index.setdefault(term, set()).add(entry.entry_id)

    def add(self, entry: MemoryEntry) -> None:
        """Add an entry to the index and persist it to the store."""
        self._store.store(entry)
        self._entries[entry.entry_id] = entry
        self._index_entry(entry)

    def persist(self) -> None:
        """Flush all in-memory entries to the store (writes updated metadata)."""
        if self._entries:
            self._store.store_batch(list(self._entries.values()))

    # -- retrieval -------------------------------------------------------------

    def retrieve(self, query: MemoryQuery) -> list[MemoryEntry]:
        """Search entries by keywords, tags, and confidence, with relevance scoring.

        Returns at most ``query.limit`` entries, sorted by descending relevance.
        Each returned entry has its ``access_count`` incremented.
        """
        if not self._entries:
            return []

        terms = tokenize(query.query)
        if not terms:
            return []

        # Collect candidate entry IDs: union of entries matching any query term.
        candidate_ids: set[str] = set()
        for term in terms:
            candidate_ids.update(self._term_index.get(term, set()))

        if not candidate_ids:
            return []

        # Score and filter candidates.
        scored: list[tuple[float, MemoryEntry]] = []
        for entry_id in candidate_ids:
            entry = self._entries[entry_id]

            # Tag filter: entry must have ALL requested tags (AND semantics).
            if query.tags and not all(t in entry.tags for t in query.tags):
                continue

            # Confidence filter.
            if entry.confidence < query.min_confidence:
                continue

            score = self._score(entry, terms)
            if score > 0:
                scored.append((score, entry))

        # Sort by score descending; stable sort preserves insertion order for ties.
        scored.sort(key=lambda pair: pair[0], reverse=True)
        results = [entry for _, entry in scored[: query.limit]]

        # Bump access tracking for returned entries.
        for entry in results:
            entry.bump_access()
        self.persist()

        return results

    def _score(self, entry: MemoryEntry, query_terms: list[str]) -> float:
        """Compute a relevance score for an entry given query terms.

        Components:
        - TF-IDF: term frequency x inverse document frequency (rarity boost)
        - Tag match bonus: +_TAG_MATCH_WEIGHT per matching tag term
        - Confidence multiplier: low-confidence entries score lower
        - Recency boost: newer entries score higher (slow 10-day decay)
        - Access boost: previously recalled entries score higher (10% per hit)
        """
        n = self.total_entries
        score = 0.0
        content_lower = entry.content.lower()
        tags_lower = [t.lower() for t in entry.tags]

        for term in query_terms:
            tf = content_lower.count(term)
            if tf > 0:
                df = len(self._term_index.get(term, set()))
                # Smoothed IDF (always positive): log(1 + N / (1 + df))
                idf = math.log(1 + n / (1 + df))
                score += tf * idf

            if term in tags_lower:
                score += _TAG_MATCH_WEIGHT

        if score == 0:
            return 0.0

        # Confidence weighting.
        score *= entry.confidence

        # Recency boost.
        if entry.created_at is not None:
            age_days = (datetime.now(UTC) - entry.created_at).total_seconds() / 86400
            recency_boost = 1.0 / (1.0 + age_days * _RECENCY_DECAY)
            score *= recency_boost

        # Access frequency boost.
        access_boost = 1.0 + entry.access_count * _ACCESS_BOOST_PER_HIT
        score *= access_boost

        return score


__all__ = [
    "MemoryIndex",
    "tokenize",
]
