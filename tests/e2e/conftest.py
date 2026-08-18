"""Shared pytest fixtures for e2e tests.

`pty_forte` drives the real `forte` CLI attached to a pseudo-terminal, so
tests that exercise prompt-toolkit's interactive entity picker
(`forte doc link-interactive`, and the follow-on link step offered by
`doc create`/`doc ingest`) can feed keystrokes the way a human at a real
terminal would, and read back what appears on screen. It is shared here
(rather than copy-pasted) because three test files need it:
`test_doc_link_interactive.py`, `test_doc_create.py`, and `test_doc_crud.py`.
"""

import os
import pty
import re
import shlex
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

# Resolve the CLI from the same virtualenv running pytest, so tests don't
# depend on `forte` being on the ambient PATH.
FORTE_BIN = Path(sys.executable).parent / "forte"

# Matches the ANSI/VT100 escape sequences (cursor moves, colors, screen
# clears) that prompt-toolkit and click emit when writing to a real
# terminal, so tests can assert on plain substrings instead of raw escape
# codes.
_ANSI_ESCAPE_RE = re.compile(
    rb"\x1b\[[0-9;?]*[a-zA-Z]"  # CSI sequences (cursor moves, colors, ...)
    rb"|\x1b\][^\x07]*(\x07|\x1b\\)"  # OSC sequences
    rb"|\x1b[()][A-Z0-9]"  # charset selection
    rb"|\x1b[=>NOM78]"  # misc single-character escapes
)


def _strip_ansi(data: bytes) -> str:
    return _ANSI_ESCAPE_RE.sub(b"", data).decode("utf-8", errors="replace")


class PtyForte:
    """A `forte` CLI subprocess attached to a pseudo-terminal.

    Lets a test feed keystrokes as a human would (`type_text`, `enter`,
    `tab`, `down`, `ctrl_c`, `ctrl_d`) and read back what appeared on the
    "screen" (`output`), with ANSI escape sequences stripped.

    A background thread continuously drains the pty's master fd into a
    buffer for as long as the process is alive. This is deliberately not
    done lazily on demand: on macOS, once the child process exits and its
    end of the pty is closed, a read of the master fd can return EOF
    without the final buffered output ever having been delivered, so any
    output produced right before the process exits (e.g. the "no entities
    to link" short-circuit, which prints nothing further) can be lost if
    nothing was actively reading at that moment.
    """

    def __init__(self, args: str, home: Path, env: dict | None = None):
        self._master_fd, slave_fd = pty.openpty()
        self.process = subprocess.Popen(
            [str(FORTE_BIN), *shlex.split(args)],
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            env={**os.environ, "HOME": str(home), **(env or {})},
            close_fds=True,
        )
        os.close(slave_fd)

        self._chunks: list[bytes] = []
        self._lock = threading.Lock()
        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()
        self._fd_closed = False

    def _read_loop(self) -> None:
        while True:
            try:
                chunk = os.read(self._master_fd, 65536)
            except OSError:
                return
            if not chunk:
                return
            with self._lock:
                self._chunks.append(chunk)

    def _write(self, data: bytes, settle: float) -> None:
        os.write(self._master_fd, data)
        time.sleep(settle)

    def type_text(self, text: str, delay: float = 0.03) -> None:
        """Type `text` one character at a time, with a small pause between
        keystrokes. prompt-toolkit's completion menu is timing-sensitive
        under a pty and can miss keystrokes sent all at once."""
        for ch in text:
            self._write(ch.encode(), delay)

    def enter(self, settle: float = 0.2) -> None:
        self._write(b"\r", settle)

    def tab(self, settle: float = 0.2) -> None:
        self._write(b"\t", settle)

    def down(self, settle: float = 0.2) -> None:
        self._write(b"\x1b[B", settle)

    def backspace(self, count: int = 1, delay: float = 0.03) -> None:
        for _ in range(count):
            self._write(b"\x7f", delay)

    def ctrl_c(self, settle: float = 0.3) -> None:
        self._write(b"\x03", settle)

    def ctrl_d(self, settle: float = 0.3) -> None:
        self._write(b"\x04", settle)

    @property
    def output(self) -> str:
        with self._lock:
            raw = b"".join(self._chunks)
        return _strip_ansi(raw)

    def wait_for(self, substring: str, timeout: float = 10) -> None:
        """Poll output until `substring` appears, or raise on timeout."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if substring in self.output:
                return
            time.sleep(0.05)
        raise AssertionError(
            f"Timed out waiting for {substring!r} in output.\n"
            f"--- output so far ---\n{self.output}"
        )

    def wait_exit(self, timeout: float = 20) -> int:
        """Wait for the process to exit, killing it (and failing loudly)
        if it hangs past `timeout` — so a mis-scripted interaction fails
        the test instead of hanging the whole suite."""
        try:
            returncode = self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
            self._reader_thread.join(timeout=2)
            self._close()
            raise AssertionError(
                f"forte process did not exit within {timeout}s.\n"
                f"--- output so far ---\n{self.output}"
            )
        self._reader_thread.join(timeout=2)
        self._close()
        return returncode

    def _close(self) -> None:
        if not self._fd_closed:
            try:
                os.close(self._master_fd)
            except OSError:
                pass
            self._fd_closed = True


@pytest.fixture
def pty_forte():
    """Factory fixture: `pty_forte(args, home, env=None)` starts `forte`
    attached to a pty and returns a `PtyForte` session. Any session a test
    forgets to `wait_exit()` is force-killed at teardown, so a mis-scripted
    interaction can never leak a hung process into the rest of the suite."""
    sessions: list[PtyForte] = []

    def _start(args: str, home: Path, env: dict | None = None) -> PtyForte:
        session = PtyForte(args, home, env=env)
        sessions.append(session)
        return session

    yield _start

    for session in sessions:
        if session.process.poll() is None:
            session.process.kill()
            try:
                session.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        session._close()
