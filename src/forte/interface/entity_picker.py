from abc import ABC, abstractmethod
from typing import Callable

from forte.model.entity import Entity


class IEntityPicker(ABC):
    """
    Interface for interactive entity selection. Implementations decide how
    (and whether) the selection session is presented to a person -- a real
    terminal-based picker, a scripted stub in tests, a future web form, etc.
    """

    @abstractmethod
    def pick(self, search: Callable[[str], list[Entity]]) -> list[Entity]:
        """
        Run an interactive selection session for entities.

        The caller provides a `search` callback to resolve entity queries.
        As the user types, the picker calls `search` with the input so far
        and displays the results; the user selects from those results.
        The picker returns the chosen entities in selection order.

        Args:
            search (Callable[[str], list[Entity]]): A function that takes a
                search query (str) and returns matching entities.

        Returns:
            (list[Entity]) The entities chosen by the user, in selection order.
                An empty list is a valid outcome: the user chose to link nothing.
        """
        pass
