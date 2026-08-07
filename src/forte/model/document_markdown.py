"""Markdown (YAML-frontmatter) serialization for processed documents.

A processed document on disk (``docs/processed/*.md``) is a markdown file:
a YAML frontmatter block carrying provenance metadata, followed by the
extracted plain text as the body. The frontmatter carries ``name``,
``source_path``, ``content_hash``, and ``ingested_at`` — enough to trace a
processed file back to the original it was extracted from and detect whether
the source content has changed.

NOTE: per solution-design, "mentions" (entity ids linked to a doc) will
eventually live as frontmatter on processed docs too, but that isn't wired up
yet — ``doc link``/``doc unlink`` write directly to the ``mentions`` table
instead. A future batch should reconcile this by also writing/reading a
``mentions`` frontmatter field here.

Pure string transforms — no filesystem or DB I/O. YAML is handled by
``pyyaml`` (``yaml.safe_load`` / ``yaml.safe_dump``). This module is the
single home for the format: the storage client writes it via
:func:`to_markdown` and the document service reads it back via
:func:`from_markdown`.
"""

from __future__ import annotations

from dataclasses import dataclass

import yaml

from forte.model.document import Document

_NAME_KEY = "name"
_SOURCE_PATH_KEY = "source_path"
_CONTENT_HASH_KEY = "content_hash"
_INGESTED_AT_KEY = "ingested_at"

_FRONTMATTER_DELIM = "---"


@dataclass
class ParsedDocument:
    """The structural content recovered from a processed-document markdown file.

    Deliberately excludes ``id``/``raw_path``/``processed_path``/``status``:
    those are not stored in the frontmatter and must be supplied by the
    caller (storage row / file location).
    """

    name: str
    source_path: str
    content_hash: str
    ingested_at: str
    body: str = ""


def to_markdown(document: Document, text: str) -> str:
    """
    Render a processed document as a YAML-frontmatter markdown document.

    Args:
        document (Document): The document whose metadata becomes frontmatter.
        text (str): The already-extracted plain text, used as the body.

    Returns:
        (str) The rendered markdown document.
    """
    front: dict[str, object] = {
        _NAME_KEY: document.name,
        _SOURCE_PATH_KEY: document.source_path,
        _CONTENT_HASH_KEY: document.content_hash,
        _INGESTED_AT_KEY: document.ingested_at,
    }

    frontmatter = yaml.safe_dump(
        front,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )

    body = text.strip()
    if body:
        return f"{_FRONTMATTER_DELIM}\n{frontmatter}{_FRONTMATTER_DELIM}\n\n{body}\n"
    return f"{_FRONTMATTER_DELIM}\n{frontmatter}{_FRONTMATTER_DELIM}\n"


def from_markdown(text: str) -> ParsedDocument:
    """
    Parse a processed-document markdown file back into its structural parts.

    Args:
        text (str): The full contents of a processed-document markdown file.

    Returns:
        (ParsedDocument) The recovered ``name``, ``source_path``,
            ``content_hash``, ``ingested_at``, and body.

    Raises:
        ValueError: if the document has no frontmatter block, the block is
            not terminated, or the frontmatter is not a YAML mapping.
    """
    frontmatter, body = _split_frontmatter(text)

    loaded = yaml.safe_load(frontmatter) or {}
    if not isinstance(loaded, dict):
        raise ValueError("document frontmatter must be a YAML mapping")

    name = loaded.get(_NAME_KEY) or ""
    source_path = loaded.get(_SOURCE_PATH_KEY) or ""
    content_hash = loaded.get(_CONTENT_HASH_KEY) or ""
    ingested_at = loaded.get(_INGESTED_AT_KEY) or ""

    return ParsedDocument(
        name=str(name),
        source_path=str(source_path),
        content_hash=str(content_hash),
        ingested_at=str(ingested_at),
        body=body,
    )


def _split_frontmatter(text: str) -> tuple[str, str]:
    """
    Split a frontmatter document into its YAML block and its body.

    Args:
        text (str): The full markdown document text.

    Returns:
        (tuple[str, str]) The frontmatter YAML and the stripped body.

    Raises:
        ValueError: if the text does not start with a ``---`` frontmatter
            block, or the block is never terminated.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != _FRONTMATTER_DELIM:
        raise ValueError("document markdown must start with a '---' frontmatter block")

    for i in range(1, len(lines)):
        if lines[i].strip() == _FRONTMATTER_DELIM:
            frontmatter = "\n".join(lines[1:i])
            body = "\n".join(lines[i + 1 :]).strip()
            return frontmatter, body

    raise ValueError("document markdown frontmatter is not terminated by '---'")
