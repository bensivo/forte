"""Mention model.

A mention is a link between a document and an entity: the fact that a given
document mentions a given entity, optionally with the exact quote that grounds
the mention. Pure data — no filesystem or DB I/O happens here.

Mentions have no error class of their own: they are always operated on through
``DocumentService``, which raises the document and entity errors defined in
:mod:`forte.model.document` and :mod:`forte.model.entity`.
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
