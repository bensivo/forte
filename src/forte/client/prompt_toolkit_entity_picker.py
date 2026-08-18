"""prompt-toolkit implementation of `IEntityPicker`.

This is the ONE module in the codebase that imports `prompt_toolkit`. It
drives an interactive, autocompleting prompt loop: as the user types, the
injected `search` callback resolves candidate entities and they are shown as
a completion menu; accepting one (or typing an exact match) appends it to the
running result list. This keeps `prompt_toolkit` -- which touches the real
terminal -- entirely out of the service layer, exactly like
`TerminalEditorSession` keeps `subprocess` out of it.
"""

from __future__ import annotations

import sys
from typing import Callable

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.input import Input
from prompt_toolkit.output import Output

from forte.interface.entity_picker import IEntityPicker
from forte.model.entity import Entity
from forte.model.entity_picker import EntityPickerAbortedError

# Cap on how many candidates are requested from `search` per keystroke, so
# the completion menu stays a menu rather than a wall of text.
_MAX_RESULTS = 15


def _format_entity(entity: Entity) -> str:
    """
    Format an entity as the display string shown in the completion menu and
    accepted into the prompt buffer.

    Args:
        entity (Entity): The entity to format.

    Returns:
        (str) A string of the form "#<id> [<schema>] <name>".
    """
    return f"#{entity.id} [{entity.schema}] {entity.name}"


class _EntityCompleter(Completer):
    """Completer that turns a `search` callback into prompt-toolkit completions.

    Each call to `get_completions` re-runs `search` against the text typed so
    far and rebuilds `display_to_entity`, a map from the exact display string
    of each candidate back to its `Entity`. That map is what lets `pick`
    resolve a submitted line to an `Entity` via a plain dict lookup instead
    of re-searching.
    """

    def __init__(self, search: Callable[[str], list[Entity]]) -> None:
        self._search = search
        self.display_to_entity: dict[str, Entity] = {}

    def get_completions(self, document: Document, complete_event: CompleteEvent):
        query = document.text_before_cursor
        results = self._search(query)[:_MAX_RESULTS]

        self.display_to_entity = {}
        for entity in results:
            display = _format_entity(entity)
            self.display_to_entity[display] = entity
            yield Completion(
                text=display,
                start_position=-len(query),
                display=display,
            )


class PromptToolkitEntityPicker(IEntityPicker):
    """Interactive terminal entity picker built on `prompt_toolkit`.

    Runs a loop over a single `PromptSession`, offering autocomplete
    suggestions from an injected `search` callback and accumulating the
    entities the user selects. `input`/`output` may be overridden (e.g. with
    prompt-toolkit's pipe input and `DummyOutput` in tests) so the session
    never needs a real terminal in unit tests.
    """

    def __init__(self, input: Input | None = None, output: Output | None = None) -> None:
        self._input = input
        self._output = output

    def pick(self, search: Callable[[str], list[Entity]]) -> list[Entity]:
        """
        Run an interactive selection session for entities.

        See `IEntityPicker.pick` for the general contract. This
        implementation raises `EntityPickerAbortedError` on Ctrl-C, and
        prompt-toolkit will fail confusingly if `stdin` is not a TTY and no
        `input` override was given -- callers should only invoke this from a
        real terminal context.

        Args:
            search (Callable[[str], list[Entity]]): A function that takes a
                search query (str) and returns matching entities.

        Returns:
            (list[Entity]) The entities chosen by the user, in selection
                order.

        Raises:
            EntityPickerAbortedError: if the user aborts the session with
                Ctrl-C.
        """
        if self._input is None and not sys.stdin.isatty():
            raise EntityPickerAbortedError("Cannot run an interactive entity picker without a TTY")

        completer = _EntityCompleter(search)
        session: PromptSession[str] = PromptSession(
            completer=completer,
            complete_while_typing=True,
            input=self._input,
            output=self._output,
        )

        picked: list[Entity] = []
        picked_ids: set[int | None] = set()

        while True:
            try:
                line = session.prompt("> ")
            except EOFError:
                break
            except KeyboardInterrupt:
                raise EntityPickerAbortedError("Entity picker aborted by user (Ctrl-C)")

            line = line.strip()
            if not line:
                break

            entity = completer.display_to_entity.get(line)
            if entity is None:
                matches = search(line)
                if len(matches) == 1:
                    entity = matches[0]
                else:
                    print("No matching entity -- try a more specific search.")
                    continue

            if entity.id in picked_ids:
                print(f"Already linked: {_format_entity(entity)}")
                continue

            picked.append(entity)
            picked_ids.add(entity.id)
            print(f"Linked: {_format_entity(entity)}")

        return picked
