"""Tests for the terminal editor-session launcher (bulk-commit boundary).

No test in this file ever spawns a real editor: `subprocess.run` is always
monkeypatched to a fake that simulates an editor process.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from forte.cli.bulk_editor import TerminalEditorSession, resolve_editor_command
from forte.services.agent import EditorAbortedError
from forte.services.config import Config


def _config(editor: str | None = None) -> Config:
    return Config(extraction_model="claude-haiku-4-5", anthropic_api_key=None, editor=editor)


class _FakeCompletedProcess:
    def __init__(self, returncode: int) -> None:
        self.returncode = returncode


# --- Precedence resolution -------------------------------------------------


def test_visual_wins_over_editor_and_config(monkeypatch):
    monkeypatch.setenv("VISUAL", "visual-editor")
    monkeypatch.setenv("EDITOR", "editor-editor")
    assert resolve_editor_command(_config(editor="config-editor")) == "visual-editor"


def test_editor_env_wins_over_config_when_visual_unset(monkeypatch):
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.setenv("EDITOR", "editor-editor")
    assert resolve_editor_command(_config(editor="config-editor")) == "editor-editor"


def test_config_wins_over_fallback_when_env_unset(monkeypatch):
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.delenv("EDITOR", raising=False)
    assert resolve_editor_command(_config(editor="config-editor")) == "config-editor"


def test_fallback_used_when_nothing_else_set(monkeypatch):
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.delenv("EDITOR", raising=False)
    monkeypatch.setattr(
        "forte.cli.bulk_editor.which",
        lambda name: "/usr/bin/nano" if name == "nano" else None,
    )
    assert resolve_editor_command(_config(editor=None)) == "nano"


def test_fallback_prefers_vi_over_nano_when_both_present(monkeypatch):
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.delenv("EDITOR", raising=False)
    monkeypatch.setattr("forte.cli.bulk_editor.which", lambda name: f"/usr/bin/{name}")
    assert resolve_editor_command(_config(editor=None)) == "vi"


def test_hardcoded_fallback_when_nothing_found_on_path(monkeypatch):
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.delenv("EDITOR", raising=False)
    monkeypatch.setattr("forte.cli.bulk_editor.which", lambda name: None)
    assert resolve_editor_command(_config(editor=None)) == "vi"


def test_blank_config_editor_falls_through_to_fallback(monkeypatch):
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.delenv("EDITOR", raising=False)
    monkeypatch.setattr("forte.cli.bulk_editor.which", lambda name: f"/usr/bin/{name}")
    assert resolve_editor_command(_config(editor=None)) == "vi"


# --- TerminalEditorSession.edit ---------------------------------------------


def test_round_trip_through_fake_editor(monkeypatch):
    monkeypatch.setenv("EDITOR", "fake-editor")
    written_paths: list[Path] = []

    def fake_run(argv):
        assert argv[0] == "fake-editor"
        path = Path(argv[-1])
        written_paths.append(path)
        assert path.exists()
        assert path.read_text(encoding="utf-8") == "original text\n"
        path.write_text("edited text\n", encoding="utf-8")
        return _FakeCompletedProcess(returncode=0)

    monkeypatch.setattr("forte.cli.bulk_editor.subprocess.run", fake_run)

    session = TerminalEditorSession(_config())
    result = session.edit("original text\n")

    assert result == "edited text\n"
    assert not written_paths[0].exists()  # cleaned up


def test_clean_exit_returns_unchanged_text_when_editor_makes_no_edits(monkeypatch):
    monkeypatch.setenv("EDITOR", "fake-editor")

    def fake_run(argv):
        return _FakeCompletedProcess(returncode=0)

    monkeypatch.setattr("forte.cli.bulk_editor.subprocess.run", fake_run)

    session = TerminalEditorSession(_config())
    result = session.edit("unchanged\n")

    assert result == "unchanged\n"


def test_editor_command_is_split_with_shlex(monkeypatch):
    monkeypatch.setenv("EDITOR", "code --wait")
    captured: dict = {}

    def fake_run(argv):
        captured["argv"] = argv
        return _FakeCompletedProcess(returncode=0)

    monkeypatch.setattr("forte.cli.bulk_editor.subprocess.run", fake_run)

    TerminalEditorSession(_config()).edit("text")

    assert captured["argv"][:-1] == ["code", "--wait"]
    assert captured["argv"][-1].endswith(".md")


def test_nonzero_exit_raises_editor_aborted_error(monkeypatch):
    monkeypatch.setenv("EDITOR", "fake-editor")
    written_paths: list[Path] = []

    def fake_run(argv):
        path = Path(argv[-1])
        written_paths.append(path)
        return _FakeCompletedProcess(returncode=1)

    monkeypatch.setattr("forte.cli.bulk_editor.subprocess.run", fake_run)

    session = TerminalEditorSession(_config())
    with pytest.raises(EditorAbortedError):
        session.edit("text")

    assert not written_paths[0].exists()  # cleaned up even on abort


def test_temp_file_cleaned_up_even_when_editor_raises(monkeypatch):
    monkeypatch.setenv("EDITOR", "fake-editor")
    written_paths: list[Path] = []

    def fake_run(argv):
        path = Path(argv[-1])
        written_paths.append(path)
        raise RuntimeError("boom")

    monkeypatch.setattr("forte.cli.bulk_editor.subprocess.run", fake_run)

    session = TerminalEditorSession(_config())
    with pytest.raises(RuntimeError):
        session.edit("text")

    assert not written_paths[0].exists()
