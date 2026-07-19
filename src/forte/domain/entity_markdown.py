"""Markdown (YAML-frontmatter) serialization for :class:`Entity`.

An entity on disk is a markdown file: a YAML frontmatter block followed by a
free-form body. The frontmatter carries the built-in structural fields
``name`` and ``aliases`` first, then each of the schema's user-defined fields
*in order* (empty values are rendered as empty, never omitted, so the file
always reflects the schema's exact field set).

What the frontmatter does NOT carry: ``id``, ``schema``, and ``file_path``.
Those are derived from context — the ``id`` comes from the SQLite row, and the
``schema`` and ``file_path`` come from the file's location on disk
(``entities/<schema>/<slug>.md``). Storing them in the frontmatter too would
just be a second, drift-prone copy.

Pure string transforms — no filesystem or DB I/O. YAML is handled by
``pyyaml`` (``yaml.safe_load`` / ``yaml.safe_dump``) rather than hand-rolled,
so values containing colons, quotes, or unicode are escaped correctly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import yaml

from forte.domain.entity import Entity

# Built-in structural fields that live in the frontmatter but are NOT part of
# the schema's user-defined ``fields`` dict.
_NAME_KEY = "name"
_ALIASES_KEY = "aliases"

_FRONTMATTER_DELIM = "---"


@dataclass
class ParsedEntity:
    """The structural content recovered from an entity markdown document.

    Deliberately excludes ``id``/``schema``/``file_path``: those are not stored
    in the frontmatter and must be supplied by the caller (DB row / file path).
    """

    name: str
    aliases: list[str] = field(default_factory=list)
    fields: dict[str, str] = field(default_factory=dict)
    body: str = ""


def to_markdown(entity: Entity) -> str:
    """Render an entity as a YAML-frontmatter markdown document.

    ``name`` and ``aliases`` come first, then each schema field in its stored
    order. Empty field values render as empty strings rather than being
    dropped, preserving the schema's structural field set on disk.
    """
    front: dict[str, object] = {
        _NAME_KEY: entity.name,
        _ALIASES_KEY: list(entity.aliases),
    }
    for key, value in entity.fields.items():
        front[key] = "" if value is None else value

    frontmatter = yaml.safe_dump(
        front,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )

    body = entity.body.strip()
    if body:
        return f"{_FRONTMATTER_DELIM}\n{frontmatter}{_FRONTMATTER_DELIM}\n\n{body}\n"
    return f"{_FRONTMATTER_DELIM}\n{frontmatter}{_FRONTMATTER_DELIM}\n"


def from_markdown(text: str) -> ParsedEntity:
    """Parse a frontmatter markdown document back into its structural parts.

    Recovers ``name``, ``aliases``, the ordered user-field dict, and the body.
    Raises :class:`ValueError` if the document has no frontmatter block.
    """
    frontmatter, body = _split_frontmatter(text)

    loaded = yaml.safe_load(frontmatter) or {}
    if not isinstance(loaded, dict):
        raise ValueError("entity frontmatter must be a YAML mapping")

    name = loaded.get(_NAME_KEY) or ""

    raw_aliases = loaded.get(_ALIASES_KEY) or []
    if not isinstance(raw_aliases, list):
        raise ValueError("entity 'aliases' must be a YAML list")
    aliases = [str(a) for a in raw_aliases]

    fields: dict[str, str] = {}
    for key, value in loaded.items():
        if key in (_NAME_KEY, _ALIASES_KEY):
            continue
        fields[str(key)] = "" if value is None else str(value)

    return ParsedEntity(name=str(name), aliases=aliases, fields=fields, body=body)


def slugify(name: str) -> str:
    """Turn a canonical entity name into an on-disk filename slug.

    Lowercases, converts whitespace runs to single hyphens, drops characters
    that are unsafe in a filename, and collapses repeated hyphens.
    """
    slug = name.strip().lower()
    slug = re.sub(r"\s+", "-", slug)
    # Keep only URL/file-safe characters; drop everything else.
    slug = re.sub(r"[^a-z0-9_-]", "", slug)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug


def _split_frontmatter(text: str) -> tuple[str, str]:
    """Split a frontmatter document into (frontmatter_yaml, body)."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != _FRONTMATTER_DELIM:
        raise ValueError("entity markdown must start with a '---' frontmatter block")

    for i in range(1, len(lines)):
        if lines[i].strip() == _FRONTMATTER_DELIM:
            frontmatter = "\n".join(lines[1:i])
            body = "\n".join(lines[i + 1 :]).strip()
            return frontmatter, body

    raise ValueError("entity markdown frontmatter is not terminated by '---'")
