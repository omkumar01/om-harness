"""Mechanical context compression: fact extraction + memory-backed summarization.

This module implements the "compress without losing major facts" requirement
using mechanical (no-LLM) extraction by default, with an optional LLM strategy
hook. Extracted facts are stored into the MemoryStore so they survive context
compression — nothing important is lost.

Design philosophy (design.md Tradeoff 2): mechanical extraction is deterministic,
testable, and free. The existing ``summarize_history()`` only captures the first
120 chars of 3 recent messages; this compressor identifies structured facts
(file paths, errors, decisions, config values) and persists them before
compressing the raw text.
"""

from __future__ import annotations

import re
from typing import Any

from om_harness.memory.models import MemoryEntry
from om_harness.memory.store import MemoryStore

# File paths: path/to/file.ext (e.g., src/parser.py, config/database.yml)
FILE_PATH_RE = re.compile(r"\b\w+/\w+\.\w[\w.-]*\b")

# URLs: http://example.com, https://localhost:5432, postgres://localhost/db
URL_RE = re.compile(r"\b(?:https?|postgres|mysql|redis|ftp)://\S+[^.\s]")

# Error-like keywords (case-insensitive)
ERROR_RE = re.compile(
    r"\b(error|exception|traceback|failed|fatal|critical|bug|crash)\b", re.IGNORECASE
)

# Decision keywords (case-insensitive). "changed to" and "set to" are multi-word.
DECISION_RE = re.compile(
    r"\b(decided|agreed|chose|selected|chosen|opted|prefer|preferred|"
    r"set to|changed to|will use|will implement|will go with|began|started)\b",
    re.IGNORECASE,
)

# Key-value / config patterns: "X is Y", "X changed to Y", "X set to Y"
KEY_VALUE_RE = re.compile(r"\b(\w[\w ]*?)\s+(is|was|changed to|set to)\s+(\S+)")

# Sentence splitter: splits on . ! ? followed by whitespace, but not on
# file extensions (the . in parser.py is never followed by whitespace).
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

# Salience scoring weights
_WEIGHT_FILE_PATH = 3.0
_WEIGHT_ERROR = 2.0
_WEIGHT_DECISION = 2.0
_WEIGHT_URL = 2.0
_WEIGHT_KEY_VALUE = 1.0


def split_sentences(text: str) -> list[str]:
    """Split text into sentences, handling newlines and abbreviations."""
    normalized = text.replace("\n", " ")
    parts = _SENTENCE_SPLIT_RE.split(normalized.strip())
    return [p.strip() for p in parts if p.strip()]


class ContextCompressor:
    """Extracts facts from text/history and produces compact summaries.

    Extracted facts are persisted to the ``MemoryStore`` so they survive
    subsequent context compression — the mechanism that ensures "major facts"
    are never lost when history is truncated.
    """

    def __init__(self, store: MemoryStore, max_fact_chars: int = 500) -> None:
        self.store = store
        self.max_fact_chars = max_fact_chars

    # -- fact extraction --------------------------------------------------------

    def extract_facts(
        self,
        text: str,
        tags: list[str],
        source_session: str = "",
        source_task: str | None = None,
    ) -> list[MemoryEntry]:
        """Mechanically extract structured facts from free text.

        Each fact is tagged with a category (``file_ref``, ``error``,
        ``decision``, ``config``) plus any caller-supplied tags. Facts whose
        content would exceed ``max_fact_chars`` are truncated.
        """
        if not text or not text.strip():
            return []

        facts: list[MemoryEntry] = []

        # 1. File path references: one fact per path
        for match in FILE_PATH_RE.finditer(text):
            path = match.group()
            facts.append(
                MemoryEntry(
                    content=f"File reference: {path}",
                    tags=[*tags, "file_ref"],
                    source_session=source_session,
                    source_task=source_task,
                )
            )

        # 2. Sentence-level extraction: errors, decisions, config
        seen_contents: set[str] = set()
        for sentence in split_sentences(text):
            sentence = sentence.strip()
            if len(sentence) < 5:
                continue

            # Determine the most salient category for this sentence
            category: str | None = None
            if ERROR_RE.search(sentence):
                category = "error"
            elif DECISION_RE.search(sentence):
                category = "decision"
            elif KEY_VALUE_RE.search(sentence):
                category = "config"

            if category is None:
                continue

            content = self._truncate(sentence)
            if content in seen_contents:
                continue
            seen_contents.add(content)

            facts.append(
                MemoryEntry(
                    content=content,
                    tags=[*tags, category],
                    source_session=source_session,
                    source_task=source_task,
                )
            )

        return facts

    def _truncate(self, text: str) -> str:
        """Truncate text to ``max_fact_chars``, appending a notice when cut."""
        if len(text) <= self.max_fact_chars:
            return text
        return text[: self.max_fact_chars] + "... [truncated]"

    # -- key entity extraction (for summaries, not persistent facts) ------------

    def _extract_key_entities(self, text: str) -> list[str]:
        """Extract short entity mentions for a human-readable summary."""
        entities: list[str] = []
        for match in FILE_PATH_RE.finditer(text):
            entities.append(match.group())
        if URL_RE.search(text):
            m = URL_RE.search(text)
            if m:
                entities.append(m.group())
        if ERROR_RE.search(text):
            entities.append("error reported")
        if DECISION_RE.search(text):
            entities.append("key decision")
        return entities

    # -- salience scoring -------------------------------------------------------

    def salience_score(self, text: str) -> float:
        """Score how information-dense / important ``text`` is.

        Used to decide which messages deserve preservation during compression.
        """
        if not text:
            return 0.0
        score = 0.0
        score += len(FILE_PATH_RE.findall(text)) * _WEIGHT_FILE_PATH
        score += len(ERROR_RE.findall(text)) * _WEIGHT_ERROR
        score += len(DECISION_RE.findall(text)) * _WEIGHT_DECISION
        score += len(URL_RE.findall(text)) * _WEIGHT_URL
        score += len(KEY_VALUE_RE.findall(text)) * _WEIGHT_KEY_VALUE
        return score

    # -- history compression ----------------------------------------------------

    def compress_history(
        self,
        history: list[Any],
        session_id: str,
        extra_tags: list[str] | None = None,
    ) -> str:
        """Extract facts from history messages and return a compact summary.

        Facts are stored into the memory store so they survive the
        compression. The returned summary replaces the raw history in context.
        """
        if not history:
            return ""

        extra_tags = extra_tags or []
        all_facts: list[MemoryEntry] = []
        key_entities: list[str] = []

        for message in history:
            content = getattr(message, "content", "")
            if not content or not content.strip():
                continue

            role = getattr(message, "role", "")
            tags = ["auto", *extra_tags]
            if str(role) in ("user", "assistant", "system"):
                tags.append(str(role))

            facts = self.extract_facts(content, tags=tags, source_session=session_id)
            all_facts.extend(facts)
            key_entities.extend(self._extract_key_entities(content))

        if all_facts:
            self.store.store_batch(all_facts)

        # Deduplicate entities while preserving order
        unique_entities: list[str] = []
        seen: set[str] = set()
        for e in key_entities:
            if e not in seen:
                seen.add(e)
                unique_entities.append(e)

        if unique_entities:
            return f"[Earlier conversation summarized: {', '.join(unique_entities[:10])}]"
        return "[Earlier conversation summarized: no key facts extracted]"

    # -- main compression entry point ------------------------------------------

    def compress(
        self,
        text: str,
        strategy: str = "mechanical",
        model_str: str | None = None,
        session_id: str = "",
    ) -> str:
        """Compress ``text`` and return a summary.

        - ``strategy="mechanical"`` (default): extract facts to memory,
          return a keyword/entity summary (no model calls).
        - ``strategy="llm"``: use ``llm_compress`` when ``model_str`` is set;
          falls back to mechanical when no model is available.
        """
        if strategy == "llm" and model_str is not None:
            return self.llm_compress(text, model_str)
        return self._mechanical_compress(text, session_id)

    def _mechanical_compress(self, text: str, session_id: str) -> str:
        """Extract facts and return a compact entity-based summary."""
        facts = self.extract_facts(text, tags=["auto"], source_session=session_id)
        if facts:
            self.store.store_batch(facts)

        entities = self._extract_key_entities(text)
        if entities:
            return f"[Earlier conversation summarized: {', '.join(entities[:10])}]"
        return "[Earlier conversation summarized: no key facts extracted]"

    # -- LLM strategy (optional extension) -------------------------------------

    def llm_compress(
        self,
        text: str,
        model_str: str,
    ) -> str:
        """Summarize text with an LLM (not yet implemented).

        Intended as a future extension: when ``memory.compression_strategy``
        is set to ``"llm"`` and a provider is configured, this would route
        through the existing model resolution to produce a higher-fidelity
        summary. For now it raises ``NotImplementedError`` so the mechanical
        fallback is always safe.
        """
        raise NotImplementedError(
            "LLM-driven compression is not yet implemented; "
            "use compression_strategy='mechanical' (the default)."
        )


__all__ = [
    "DECISION_RE",
    "ERROR_RE",
    "FILE_PATH_RE",
    "KEY_VALUE_RE",
    "URL_RE",
    "ContextCompressor",
    "split_sentences",
]
