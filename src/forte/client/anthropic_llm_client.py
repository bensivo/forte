import anthropic

from forte.interface.llm_client import ILlmClient
from forte.model.llm import LlmResponse, Usage


class AnthropicLlmClient(ILlmClient):
    """
    Real ILlmClient implementation over the Anthropic Python SDK.

    A thin pass-through: it constrains the model to schema-shaped JSON via
    ``output_config`` and returns the first text block plus token usage. It
    sends no ``temperature``/``top_p``/``top_k`` or ``thinking`` config. The
    SDK's own 429/5xx retries apply; the malformed-JSON retry policy lives in
    the structured-call helper above this boundary (service layer).
    """

    def __init__(self, model: str, api_key: str, max_tokens: int = 4096) -> None:
        self._model = model
        self._max_tokens = max_tokens
        self._client = anthropic.Anthropic(api_key=api_key)

    def messages(self, *, system: str, user: str, schema: dict) -> LlmResponse:
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
        return LlmResponse(text=text, usage=usage)
