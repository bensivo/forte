"""Feature-neutral errors for the entity picker seam.

These are used by any feature that needs to present a human with an
interactive selection session to choose entities (currently only the entity
linking flow, but the errors themselves carry no linking-specific meaning).
"""

from __future__ import annotations


class EntityPickerError(Exception):
    """Base class for entity picker errors."""


class EntityPickerAbortedError(EntityPickerError):
    """Raised when the selection session is aborted by the user.

    Signals that the interactive picking session was terminated before
    completion (e.g. the user pressed Ctrl-C or otherwise exited) rather
    than closed with a selection result.
    """
