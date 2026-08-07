from abc import ABC, abstractmethod

from forte.model.llm import LlmResponse


class ILlmClient(ABC):
    """
    Interface for the low-level LLM boundary used by the agent pipeline.
    Implementations send one system+user+schema request to a model and
    return the raw JSON text it produced plus token usage. They do not
    parse the text into domain objects, and do not implement retry or
    validation logic — that is business logic that lives in the service
    layer above this boundary.
    """

    @abstractmethod
    def messages(self, *, system: str, user: str, schema: dict) -> LlmResponse:
        """
        Send one structured-output request and return the raw JSON text
        plus usage.

        Args:
            system (str): The system prompt.
            user (str): The user prompt.
            schema (dict): A JSON schema describing the required output shape.

        Returns:
            (LlmResponse) The raw text produced by the model, plus token usage.
        """
        pass
