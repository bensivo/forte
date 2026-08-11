from abc import ABC, abstractmethod


class IEditor(ABC):
    """
    Interface for presenting text to a human for editing. Implementations
    decide how (and whether) `text` is actually shown to a person -- a real
    terminal editor, a scripted stub in tests, a future web textarea, etc.
    """

    @abstractmethod
    def edit(self, text: str) -> str:
        """
        Present `text` for editing and return the edited contents.

        Args:
            text (str): The text to present for editing.

        Returns:
            (str) The edited contents.
        """
        pass
