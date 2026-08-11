"""Terminal-launcher implementation of `IEditor`.

This is the ONE place in the stack that spawns a real text editor. The editor
doesn't trigger any behavior of its own -- it's a low-level operation against
an external dependency (`vim`, `code --wait`, etc.) that happens to be
*called by* services, exactly like any other injected client. That makes it a
client, not a controller: `main.py` constructs a single `TerminalEditorSession`
and injects it wherever an `IEditor` is needed, and it is trivial to swap for
a scripted stub in tests.

Editor resolution follows git-style precedence:

    $VISUAL -> $EDITOR -> Config.editor -> hardcoded fallback chain (vi, nano)

The fallback chain is only consulted when none of `$VISUAL`, `$EDITOR`, or
`Config.editor` are set; the first fallback candidate found on `PATH` wins.
Editor command strings are split with `shlex.split` so values like
``"code --wait"`` work (GUI editors need their own wait flag to block the
subprocess until the user closes the file).
"""

from __future__ import annotations

import os
import shlex
import subprocess
import tempfile
from pathlib import Path
from shutil import which

from forte.interface.editor import IEditor
from forte.model.editor import EditorAbortedError
from forte.service.config_service import ConfigService

_FALLBACK_EDITORS = ("vi", "nano")


def resolve_editor_command(config_service: ConfigService) -> str:
    """Resolve the editor command string via the documented precedence.

    Order: `$VISUAL` -> `$EDITOR` -> `config.editor` -> the first of the
    hardcoded fallback chain (`vi`, then `nano`) found on `PATH`. If none of
    the fallback candidates are found on `PATH` either, the first fallback
    (`vi`) is returned anyway so callers get a deterministic value.

    Args:
        config_service (ConfigService): Resolves the vault's configuration,
            consulted for its `editor` key only after `$VISUAL`/`$EDITOR`
            are checked and found unset.

    Returns:
        (str) The resolved editor command string.

    Raises:
        NoDefaultVaultError: if no vault is selected (propagated from the
            injected ConfigService), but only when `$VISUAL`/`$EDITOR` are
            both unset and the config must actually be consulted.
    """
    visual = os.environ.get("VISUAL")
    if visual:
        return visual

    editor_env = os.environ.get("EDITOR")
    if editor_env:
        return editor_env

    config = config_service.get_config()
    if config.editor:
        return config.editor

    for candidate in _FALLBACK_EDITORS:
        if which(candidate) is not None:
            return candidate

    return _FALLBACK_EDITORS[0]


class TerminalEditorSession(IEditor):
    """Launches the resolved editor command as a subprocess against a temp file.

    Writes `text` to a temporary `.md` file, runs the resolved editor command
    against it, waits for it to exit, and reads back the (possibly edited)
    file contents. The temp file is always cleaned up, even if the editor
    aborts.
    """

    def __init__(self, config_service: ConfigService) -> None:
        self._config_service = config_service

    def edit(self, text: str) -> str:
        editor_command = resolve_editor_command(self._config_service)
        argv = shlex.split(editor_command)

        fd, tmp_name = tempfile.mkstemp(suffix=".md", prefix="forte-bulk-commit-")
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)

            result = subprocess.run([*argv, str(tmp_path)])
            if result.returncode != 0:
                raise EditorAbortedError(
                    f"Editor {editor_command!r} exited with status {result.returncode}"
                )

            return tmp_path.read_text(encoding="utf-8")
        finally:
            tmp_path.unlink(missing_ok=True)
