"""Terminal-launcher implementation of the editor-session seam.

This is the ONE place in the CLI that spawns a real text editor. It
implements the `EditorSession` protocol (`forte.services.agent.EditorSession`)
so the bulk-commit orchestrator itself never imports `subprocess` or
`tempfile` -- see `forte/services/agent/_editor.py` for the seam this fills.

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

from forte.services.agent import EditorAbortedError
from forte.services.config import Config

_FALLBACK_EDITORS = ("vi", "nano")


def resolve_editor_command(config: Config) -> str:
    """Resolve the editor command string via the documented precedence.

    Order: `$VISUAL` -> `$EDITOR` -> `config.editor` -> the first of the
    hardcoded fallback chain (`vi`, then `nano`) found on `PATH`. If none of
    the fallback candidates are found on `PATH` either, the first fallback
    (`vi`) is returned anyway so callers get a deterministic value.
    """
    visual = os.environ.get("VISUAL")
    if visual:
        return visual

    editor_env = os.environ.get("EDITOR")
    if editor_env:
        return editor_env

    if config.editor:
        return config.editor

    for candidate in _FALLBACK_EDITORS:
        if which(candidate) is not None:
            return candidate

    return _FALLBACK_EDITORS[0]


class TerminalEditorSession:
    """Launches the resolved editor command as a subprocess against a temp file.

    Writes `text` to a temporary `.md` file, runs the resolved editor command
    against it, waits for it to exit, and reads back the (possibly edited)
    file contents. The temp file is always cleaned up, even if the editor
    aborts.
    """

    def __init__(self, config: Config) -> None:
        self._config = config

    def edit(self, text: str) -> str:
        editor_command = resolve_editor_command(self._config)
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
