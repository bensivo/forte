"""The editor-session seam: the bulk-commit flow's only text-editor surface.

The bulk flow is the DEFAULT review flow (the one-at-a-time flow is opt-in
via ``--interactive``/``-i``). It collapses the two sequential review points
of the pipeline into a single pass: it renders every proposed change (new
entities, links, field updates) into one text document, hands that document
to an :class:`EditorSession`, and parses whatever text comes back into
decisions. The orchestrator never spawns a subprocess, writes a temp file, or
knows anything about ``$VISUAL``/``$EDITOR``/config precedence -- it only ever
depends on the `EditorSession` protocol defined here, exactly as it depends on
`Reviewer` for the one-at-a-time flow.

This module intentionally has NO Click, NO Rich, NO subprocess, and NO
tempfile imports. Those concerns belong entirely to the concrete terminal
launcher in the controller layer, which is NOT implemented here.

``EditorAbortedError`` -- the error an implementation raises when the session
is aborted rather than closed cleanly -- lives in :mod:`forte.model.agent`
with the rest of the agent errors, per the style guide.
"""

from __future__ import annotations

import typing


class EditorSession(typing.Protocol):
    """The bulk-commit flow's only text-editor surface.

    Implementations decide how (and whether) to present `text` to a human
    for editing. The orchestrator only ever calls `edit` and only ever
    consumes the returned string -- it has no knowledge of how the edit
    happened (a real terminal editor, a scripted stub in tests, a future web
    textarea, etc.).
    """

    def edit(self, text: str) -> str:
        """Present `text` for editing and return the edited contents.

        Raises:
            EditorAbortedError: if the editing session was aborted rather
                than closed cleanly.
        """
        ...
