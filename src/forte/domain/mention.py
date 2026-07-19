"""Mention domain model.

A mention is a link between a document and an entity: the fact that a given
document mentions a given entity, optionally with the exact quote that
grounds the mention. Pure data — no filesystem or DB I/O happens here.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Mention:
    """A single doc-entity mention link."""

    doc_id: int
    entity_id: int
    quote: str
    created_at: str
