"""The editor-session seam: the bulk-commit flow's only text-editor surface.

Bulk-commit mode (``--bulk-commit``) collapses the two sequential review
points of the default pipeline into a single pass: it renders every proposed
change (new entities, links, field updates) into one text document, hands
that document to an :class:`EditorSession`, and parses whatever text comes
back into decisions. The orchestrator never spawns a subprocess, writes a
temp file, or knows anything about ``$VISUAL``/``$EDITOR``/config
precedence -- it only ever depends on the `EditorSession` protocol defined
here, exactly as it depends on `Reviewer` for the one-at-a-time flow.

This module intentionally has NO Click, NO Rich, NO subprocess, and NO
tempfile imports. Those concerns belong entirely to the concrete terminal
launcher in the driver layer (`forte.cli.bulk_editor`), which is a separate
module/task and is NOT implemented here.
"""

from __future__ import annotations

import typing


class EditorAbortedError(Exception):
    """Raised when the user's editor process exits non-zero.

    Signals that the editor session was aborted (e.g. the user quit with an
    error, such as ``:cq`` in vim) rather than closed cleanly. Callers must
    treat this as "commit nothing" -- the bulk orchestrator lets it propagate
    unchanged since nothing has been committed by the time the editor runs.
    """


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
