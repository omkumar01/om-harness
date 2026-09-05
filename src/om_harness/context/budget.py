"""Token accounting: estimation heuristic and per-run context ledger."""

from __future__ import annotations

from pydantic import BaseModel, Field

# ~4 characters per token is a good enough estimator for budgeting and
# reporting; exact counts are taken from provider usage data when available.
CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // CHARS_PER_TOKEN)


class ContextReport(BaseModel):
    """What was sent to the model, by component, in estimated tokens."""

    items: dict[str, int] = Field(default_factory=dict)
    total_tokens: int = 0


class ContextLedger:
    """Accumulates estimated token counts per context component."""

    def __init__(self) -> None:
        self._items: dict[str, int] = {}

    def record(self, category: str, text: str) -> int:
        tokens = estimate_tokens(text)
        self._items[category] = self._items.get(category, 0) + tokens
        return tokens

    def record_tokens(self, category: str, tokens: int) -> None:
        self._items[category] = self._items.get(category, 0) + tokens

    def report(self) -> ContextReport:
        return ContextReport(items=dict(self._items), total_tokens=sum(self._items.values()))
