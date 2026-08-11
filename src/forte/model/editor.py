"""Feature-neutral errors for the editor seam.

These are used by any feature that needs to hand text to a human via an
external text editor (currently only the agent bulk-commit flow, but the
errors themselves carry no agent-specific meaning).
"""

from __future__ import annotations


class EditorError(Exception):
    """Base class for editor errors."""


class EditorAbortedError(EditorError):
    """Raised when the editor process exits non-zero.

    Signals that the editing session was aborted (e.g. the user quit with an
    error, such as ``:cq`` in vim) rather than closed cleanly.
    """
