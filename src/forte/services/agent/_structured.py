"""Bounded-retry structured-call helper over :class:`LLMClient`.

This is the reusable "LLM fills a structured blank" primitive every pipeline
step calls. It sits directly above the low-level ``messages()`` boundary:
it invokes the client, hands the raw JSON text to a caller-supplied ``parse``
callback (which parses/validates and raises on anything malformed or
wrong-shaped), and returns the validated object plus token usage.

The retry policy lives here, in exactly one place: any failure — a transport
error from ``messages()``, a :class:`json.JSONDecodeError`, or a validation
error raised by ``parse`` — is retried up to :data:`MAX_RETRIES` attempts. When
all attempts are exhausted it raises :class:`StructuredCallError` chained from
the last underlying failure; it never swallows it, so a failing step aborts the
whole run with nothing committed.

``parse`` is a generic callback so this module stays independent of the
per-step/domain schemas.
"""

from __future__ import annotations

from typing import Callable, TypeVar

from ._usage import Usage

T = TypeVar("T")

MAX_RETRIES = 5


class StructuredCallError(Exception):
    """Raised when a structured call fails all retries; carries the last error."""

    def __init__(self, message: str, last_error: Exception) -> None:
        super().__init__(message)
        self.last_error = last_error


def structured_call(
    llm,
    *,
    system: str,
    user: str,
    schema: dict,
    parse: Callable[[str], T],
) -> tuple[T, Usage]:
    """Call the LLM and parse/validate its output, retrying up to MAX_RETRIES.

    Each attempt calls ``llm.messages(...)`` then ``parse(resp.text)``. Any
    exception from either — transport error, JSON decode error, or a validation
    error raised by ``parse`` — triggers a retry. After all attempts fail,
    raises :class:`StructuredCallError` chained from the last exception. On
    success returns ``(parsed, resp.usage)``.
    """
    last_error: Exception | None = None
    for _ in range(MAX_RETRIES):
        try:
            resp = llm.messages(system=system, user=user, schema=schema)
            parsed = parse(resp.text)
        except Exception as exc:  # noqa: BLE001 - policy: retry on any failure
            last_error = exc
            continue
        return parsed, resp.usage

    assert last_error is not None
    raise StructuredCallError(
        f"Structured call failed after {MAX_RETRIES} attempts: {last_error}",
        last_error,
    ) from last_error
