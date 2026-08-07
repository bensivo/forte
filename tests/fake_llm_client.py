"""Test double for ``ILlmClient`` (``forte.interface.llm_client``).

Kept in ``tests/`` rather than ``client/`` because it exists purely to give
the test suite a deterministic, network-free stand-in for the real Anthropic
client — it is not a production implementation of the interface.
"""

from __future__ import annotations

from forte.model.llm import LlmResponse, Usage


class StubLlmClient:
    """Test double: returns queued responses per ``messages()`` call, in order.

    Each item in ``responses`` is either an :class:`LlmResponse`, a raw ``str``
    (wrapped as an ``LlmResponse`` with zero usage), or an ``Exception``
    instance (raised when reached, simulating a transport error). This lets
    tests script malformed JSON and failures to drive the retry/validate path.

    Satisfies ``ILlmClient`` structurally (duck-typed), so it can be injected
    anywhere an ``ILlmClient`` is expected without inheriting from it.
    """

    def __init__(self, responses: list) -> None:
        self._responses = list(responses)
        self._index = 0

    def messages(self, *, system: str, user: str, schema: dict) -> LlmResponse:
        if self._index >= len(self._responses):
            raise IndexError("StubLlmClient exhausted: no more scripted responses.")
        item = self._responses[self._index]
        self._index += 1
        if isinstance(item, Exception):
            raise item
        if isinstance(item, LlmResponse):
            return item
        if isinstance(item, str):
            return LlmResponse(text=item, usage=Usage.zero())
        raise TypeError(f"Unsupported scripted response type: {type(item)!r}")
