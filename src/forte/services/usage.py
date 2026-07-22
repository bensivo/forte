"""Token-usage accounting shared across the agent pipeline.

``Usage`` is both the per-call usage value (returned by the LLM boundary) and
the run-level accumulator (summed across every LLM call in an ``agent process``
run). It is deliberately tiny and dependency-free so every layer — the LLM
client, the pipeline domain models, the orchestrator, and the cost reporter —
can share one vocabulary for tokens without importing each other.

Cost/pricing lives elsewhere (the cost-reporting step); this module only counts
tokens.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Usage:
    """Token counts for one LLM call, or a sum across many.

    Fields mirror the Anthropic SDK's ``response.usage``. Instances are
    immutable; combine them with ``+`` or :meth:`add` (both return a new
    ``Usage``) rather than mutating in place.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0

    def __add__(self, other: Usage) -> Usage:
        if not isinstance(other, Usage):
            return NotImplemented
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
            cache_creation_tokens=self.cache_creation_tokens + other.cache_creation_tokens,
        )

    def add(self, other: Usage) -> Usage:
        """Return the sum of this usage and ``other`` (alias for ``+``)."""
        return self + other

    @classmethod
    def zero(cls) -> Usage:
        """Return an empty usage total (the additive identity)."""
        return cls()
