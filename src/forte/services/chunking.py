"""Service layer: deterministic, structure-aware text chunking for search indexing.

Pure functions of ``(text, max_chars) -> list[str]`` — no DB, no embedding
client, no Click/Rich knowledge — so the same chunker is reused identically
for processed-doc bodies and entity markdown bodies. Callers pass
already-extracted body text; this module never parses or emits YAML
frontmatter.

Splitting is structure-aware, not a fixed-token window: the input is first
broken into blocks on markdown heading boundaries (lines starting with
``#``) and blank-line paragraph boundaries, then consecutive blocks are
packed together up to ``max_chars`` without splitting mid-paragraph where
avoidable. A single block that itself exceeds ``max_chars`` is hard-split
into ``<= max_chars`` pieces as a fallback.
"""

from __future__ import annotations

DEFAULT_MAX_CHARS = 1000


def chunk_text(text: str, max_chars: int = DEFAULT_MAX_CHARS) -> list[str]:
    """Split ``text`` into an ordered list of structure-aware chunks.

    Behavior:
      - The input is split into blocks on markdown heading lines (lines
        whose stripped content starts with ``#``) and on blank-line
        paragraph breaks.
      - Consecutive blocks are packed into a chunk, joined by a blank line,
        until adding the next block would exceed ``max_chars``.
      - A single block that exceeds ``max_chars`` on its own is hard-split
        into ``<= max_chars``-length pieces (fallback for oversized
        paragraphs); it does not get merged with neighboring blocks.
      - Empty or whitespace-only input returns an empty list — this is a
        valid result, not an error.

    The returned list is ordered; callers assign ``chunk_index`` by
    position. This function is pure and deterministic: the same input
    always yields the same output.

    Args:
      text: already-extracted body text (no frontmatter).
      max_chars: soft cap on chunk size, in characters. Defaults to
        ``DEFAULT_MAX_CHARS``.

    Raises:
      - ValueError: ``max_chars`` is not positive.
    """
    if max_chars <= 0:
        raise ValueError(f"max_chars must be positive, got {max_chars}")

    if not text or not text.strip():
        return []

    blocks = _split_into_blocks(text)

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for block in blocks:
        if len(block) > max_chars:
            if current:
                chunks.append("\n\n".join(current))
                current = []
                current_len = 0
            chunks.extend(_hard_split(block, max_chars))
            continue

        sep_len = 2 if current else 0  # "\n\n" separator between blocks
        if current and current_len + sep_len + len(block) > max_chars:
            chunks.append("\n\n".join(current))
            current = []
            current_len = 0
            sep_len = 0

        current.append(block)
        current_len += sep_len + len(block)

    if current:
        chunks.append("\n\n".join(current))

    return chunks


def chunk_text_with_index(
    text: str, max_chars: int = DEFAULT_MAX_CHARS
) -> list[tuple[int, str]]:
    """Convenience wrapper pairing each chunk from :func:`chunk_text` with its index.

    Returns a list of ``(chunk_index, chunk_text)`` tuples, ``chunk_index``
    starting at 0 in document order.
    """
    return list(enumerate(chunk_text(text, max_chars=max_chars)))


def _split_into_blocks(text: str) -> list[str]:
    """Split ``text`` into blocks on heading lines and blank-line breaks.

    A heading line (stripped content starting with ``#``) always starts a
    new block, even mid-paragraph. A blank line ends the current block
    without starting a new one immediately. Each returned block has its
    surrounding whitespace stripped; empty blocks are dropped.
    """
    blocks: list[str] = []
    current: list[str] = []

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            if current:
                blocks.append("\n".join(current).strip())
                current = []
            current.append(line)
        elif stripped == "":
            if current:
                blocks.append("\n".join(current).strip())
                current = []
        else:
            current.append(line)

    if current:
        blocks.append("\n".join(current).strip())

    return [block for block in blocks if block]


def _hard_split(block: str, max_chars: int) -> list[str]:
    """Split ``block`` into consecutive ``<= max_chars``-length pieces."""
    return [block[i : i + max_chars] for i in range(0, len(block), max_chars)]
