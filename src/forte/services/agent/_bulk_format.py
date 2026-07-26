"""The bulk-commit editor document format: render proposals, parse decisions.

``--bulk-commit`` replaces the one-at-a-time :class:`~forte.services.agent.
_review.Reviewer` prompt with a single git-style editor session: every
proposed change (new entities, links, field updates) is rendered into one
text document, handed to an editor, and the edited text is parsed back into
one :class:`~forte.services.agent._pipeline_models.Decision` per proposal.

This module is the pure serialize/parse core of that format. It has NO
Click, Rich, filesystem, or DB imports -- ``render`` takes a list of
in-memory :data:`ProposedChange` and returns a ``str``; ``parse`` takes that
``str`` (possibly hand-edited) back to a ``list[Decision]``. The actual
editor subprocess is a separate boundary (``_editor.py`` /
``cli/bulk_editor.py``, a different task).

Change-id scheme
-----------------
Every proposal line carries an opaque, stable token -- ``c0``, ``c1``, ``c2``,
... -- assigned by :func:`render` from the proposal's **index in the
``changes`` list**, not from its position within a section. :func:`parse`
is handed that same ``changes`` list and keys off this token, so it never
has to reconstruct a proposal from human-editable text. This is what lets
the rest of the line (wording, quotes, the display-only existing-entity id
on link lines) be freely edited or garbled by the user without breaking the
approve/reject mapping, and it's why matching is independent of line order:
a user can reorder, delete, or duplicate lines and only the ``[y]``/``[n]``
token attached to each still-present change-id token is consulted.

Empty-section choice
---------------------
All three section headers (``## New entities``, ``## Links to existing
entities``, ``## Field updates``) are always printed, even when a section
has no proposals -- an empty section shows a single ``(none)`` comment line
instead of proposal lines. This keeps the document's structure predictable
(three sections, always in the same order) regardless of what got proposed,
which is easier to skim and easier to test than a document whose section
count varies.

Action-token rules (consumed by :func:`parse`)
------------------------------------------------
- ``[y]`` -> approved.
- ``[n]`` -> rejected.
- A change-id that no longer appears anywhere in the edited text (the user
  deleted the line) -> rejected.
- Any other action token -- blank, misspelled, ``[x]``, whatever -- is
  treated the same as "not approved" -> rejected. Nothing but an exact
  ``[y]`` commits a change; this is a deliberately conservative default so a
  garbled edit never silently approves something.
- Lines that don't match the ``[<action>] <change-id>`` shape (the header
  comment block, ``## Section`` lines, blank lines, and the indented ``#
  alias/field/quote`` detail lines under a proposal) are ignored entirely --
  they carry no change-id and never enter the decision map.
"""

from __future__ import annotations

import re

from ._pipeline_models import (
    Decision,
    ProposedChange,
    ProposedFieldSet,
    ProposedLink,
    ProposedNewEntity,
)

_HEADER = """\
###############
# Extracted Entity Bulk Commit.
#
# Review all proposed changes below. Each line is pre-filled with [y],
# meaning "apply this change". To reject a change, edit its [y] to [n], or
# just delete the line -- a deleted line is treated exactly like [n].
# A line whose action is anything other than [y] (blank, garbled, [x], ...)
# is also treated as rejected -- only an exact [y] commits a change.
#
# You can only accept or skip the changes proposed below. You cannot add a
# brand-new record by typing a line, and you cannot convert a "link to
# existing entity" into a "new entity" (or vice versa) by editing this file.
# Field values shown here are informational and cannot be edited inline --
# use `forte entity edit` after committing to make corrections.
#
# When you are done, save and close the editor to commit every [y] change.
###############
"""

_NONE_PLACEHOLDER = "# (none proposed)"

# Matches a proposal line: optional leading whitespace, "[<action>]", then
# whitespace, then the change-id token (first non-whitespace run after the
# brackets). Everything after the change-id (the human-readable description)
# is irrelevant to parsing.
_LINE_RE = re.compile(r"^\s*\[(?P<action>[^\]]*)\]\s+(?P<change_id>\S+)")


def _change_id(index: int) -> str:
    return f"c{index}"


def render(changes: list[ProposedChange]) -> str:
    """Render ``changes`` into the bulk-commit editor document.

    Every change is assigned a stable ``c<index>`` token from its position
    in ``changes`` (see module docstring), then grouped by kind into three
    sections. Each proposal line starts pre-filled with ``[y]``.
    """
    new_entity_lines: list[str] = []
    link_lines: list[str] = []
    field_set_lines: list[str] = []

    for index, change in enumerate(changes):
        change_id = _change_id(index)
        if isinstance(change, ProposedNewEntity):
            new_entity_lines.extend(_render_new_entity(change_id, change))
        elif isinstance(change, ProposedLink):
            link_lines.extend(_render_link(change_id, change))
        elif isinstance(change, ProposedFieldSet):
            field_set_lines.extend(_render_field_set(change_id, change))
        else:  # pragma: no cover - exhaustiveness guard
            raise TypeError(f"Unknown proposed change type: {type(change)!r}")

    parts: list[str] = [_HEADER]
    parts.append("## New entities")
    parts.append("\n".join(new_entity_lines) if new_entity_lines else _NONE_PLACEHOLDER)
    parts.append("")
    parts.append("## Links to existing entities")
    parts.append("\n".join(link_lines) if link_lines else _NONE_PLACEHOLDER)
    parts.append("")
    parts.append("## Field updates")
    parts.append("\n".join(field_set_lines) if field_set_lines else _NONE_PLACEHOLDER)
    parts.append("")

    return "\n".join(parts)


def _render_new_entity(change_id: str, change: ProposedNewEntity) -> list[str]:
    lines = [f"[y] {change_id}  New {change.schema} entity: {change.name}"]
    if change.aliases:
        lines.append(f"    # aliases: {', '.join(change.aliases)}")
    if change.fields:
        fields_str = ", ".join(f"{k}={v}" for k, v in change.fields.items())
        lines.append(f"    # fields: {fields_str}")
    _append_quote(lines, change.supporting_quote)
    return lines


def _render_link(change_id: str, change: ProposedLink) -> list[str]:
    lines = [
        f"[y] {change_id}  Link '{change.candidate_name}' -> existing "
        f"{change.schema} #{change.entity_id} ({change.entity_name})"
    ]
    _append_quote(lines, change.supporting_quote)
    return lines


def _render_field_set(change_id: str, change: ProposedFieldSet) -> list[str]:
    target = change.target
    fields_str = ", ".join(f"{k}={v}" for k, v in change.fields.items())
    lines = [
        f"[y] {change_id}  Set fields on {target.schema} '{target.name}': {fields_str}"
    ]
    return lines


def _append_quote(lines: list[str], quote: str) -> None:
    if quote:
        lines.append(f'    # quote: "{quote}"')


def parse(edited: str, changes: list[ProposedChange]) -> list[Decision]:
    """Parse the (possibly hand-edited) document back into decisions.

    Returns exactly one :class:`Decision` per entry in ``changes``, in the
    same order as ``changes`` -- independent of how the lines were ordered,
    edited, or deleted in ``edited``. See the module docstring for the
    action-token rules.
    """
    approved_by_id: dict[str, bool] = {}
    for line in edited.splitlines():
        match = _LINE_RE.match(line)
        if not match:
            continue
        action = match.group("action").strip().lower()
        change_id = match.group("change_id")
        approved_by_id[change_id] = action == "y"

    decisions: list[Decision] = []
    for index, change in enumerate(changes):
        change_id = _change_id(index)
        approved = approved_by_id.get(change_id, False)
        decisions.append(Decision(change=change, approved=approved))
    return decisions
