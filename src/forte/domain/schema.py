"""Schema domain model.

An immutable description of an entity kind and its user-defined fields.
Pure data — no I/O happens here.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Schema:
    """A named entity kind and its ordered, free-text field names."""

    name: str
    fields: list[str] = field(default_factory=list)
