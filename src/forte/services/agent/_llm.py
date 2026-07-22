"""LLM client abstraction with a stubbable low-level ``messages()`` boundary.

The agent pipeline talks to the model through a narrow :class:`LLMClient`
protocol whose single method, ``messages()``, is deliberately low-level: it
takes a system prompt, a user prompt, and a JSON schema describing the required
output, and returns the *raw* JSON text the model produced plus token
:class:`~forte.services.agent._usage.Usage`. It does **not** parse into domain
objects — that lives one layer up in the structured-call helper — so tests can
stub this boundary and inject malformed or schema-violating JSON to exercise
the parse/validate/retry path on real bytes.

:class:`AnthropicLLMClient` is the real, thin pass-through over the Anthropic
SDK (structured output via ``output_config``); :class:`StubLLMClient` scripts
canned responses and transport-style errors for deterministic, free tests.
"""

from __future__ import annotations

import typing
from dataclasses import dataclass

import anthropic

from ._usage import Usage


@dataclass(frozen=True)
class LLMResponse:
    """The raw text a model produced for one call, plus its token usage."""

    text: str
    usage: Usage


class LLMClient(typing.Protocol):
    """Narrow LLM boundary: one system+user+schema request, raw text + usage out."""

    def messages(self, *, system: str, user: str, schema: dict) -> LLMResponse:
        """Send one structured-output request and return the raw JSON text + usage."""
        ...


class AnthropicLLMClient:
    """Real :class:`LLMClient` over the Anthropic Python SDK.

    A thin pass-through: it constrains the model to schema-shaped JSON via
    ``output_config`` and returns the first text block plus token usage. It
    sends no ``temperature``/``top_p``/``top_k`` or ``thinking`` config. The
    SDK's own 429/5xx retries apply; the malformed-JSON retry policy lives in
    the structured-call helper above this boundary.
    """

    def __init__(self, model: str, api_key: str, max_tokens: int = 4096) -> None:
        self._model = model
        self._max_tokens = max_tokens
        self._client = anthropic.Anthropic(api_key=api_key)

    def messages(self, *, system: str, user: str, schema: dict) -> LLMResponse:
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"format": {"type": "json_schema", "schema": schema}},
        )
        text = next(b.text for b in resp.content if b.type == "text")
        usage = Usage(
            input_tokens=getattr(resp.usage, "input_tokens", 0) or 0,
            output_tokens=getattr(resp.usage, "output_tokens", 0) or 0,
            cache_read_tokens=getattr(resp.usage, "cache_read_input_tokens", 0) or 0,
            cache_creation_tokens=getattr(resp.usage, "cache_creation_input_tokens", 0) or 0,
        )
        return LLMResponse(text=text, usage=usage)


class StubLLMClient:
    """Test double: returns queued responses per ``messages()`` call, in order.

    Each item in ``responses`` is either an :class:`LLMResponse`, a raw ``str``
    (wrapped as an ``LLMResponse`` with zero usage), or an ``Exception``
    instance (raised when reached, simulating a transport error). This lets
    tests script malformed JSON and failures to drive the retry/validate path.
    """

    def __init__(self, responses: list) -> None:
        self._responses = list(responses)
        self._index = 0

    def messages(self, *, system: str, user: str, schema: dict) -> LLMResponse:
        if self._index >= len(self._responses):
            raise IndexError("StubLLMClient exhausted: no more scripted responses.")
        item = self._responses[self._index]
        self._index += 1
        if isinstance(item, Exception):
            raise item
        if isinstance(item, LLMResponse):
            return item
        if isinstance(item, str):
            return LLMResponse(text=item, usage=Usage.zero())
        raise TypeError(f"Unsupported scripted response type: {type(item)!r}")
