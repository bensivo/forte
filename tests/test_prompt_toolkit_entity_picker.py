from typing import Callable

import pytest
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from forte.client.prompt_toolkit_entity_picker import PromptToolkitEntityPicker
from forte.model.entity import Entity
from forte.model.entity_picker import EntityPickerAbortedError

ALICE = Entity(id=1, schema="person", name="Alice")
ACME = Entity(id=4, schema="client", name="Acme Corp")
_ENTITIES = [ALICE, ACME]


def _search(query: str) -> list[Entity]:
    """Fake substring search over the fixture entities' names."""
    query = query.lower().strip()
    if not query:
        return list(_ENTITIES)
    return [e for e in _ENTITIES if query in e.name.lower()]


def _run(keys: list[str], search: Callable[[str], list[Entity]] = _search) -> list[Entity]:
    """
    Drive `PromptToolkitEntityPicker.pick` with scripted keystrokes over a
    pipe input and a dummy (non-rendering) output, so the session never
    touches a real terminal.

    Args:
        keys (list[str]): Chunks of raw input text/keys to feed the pipe, in
            order (e.g. `["ali", "\\t", "\\r"]` types "ali", hits Tab to
            complete, then Enter to submit).
        search (Callable[[str], list[Entity]]): The search callback to pass
            through to `pick`.

    Returns:
        (list[Entity]) Whatever `pick` returned.
    """
    with create_pipe_input() as pipe_input:
        for chunk in keys:
            pipe_input.send_text(chunk)
        picker = PromptToolkitEntityPicker(input=pipe_input, output=DummyOutput())
        return picker.pick(search)


def test_pick_one():
    # Given/When: the user types a query, Tab-completes the sole match, and
    # submits, then submits an empty line to finish
    result = _run(["ali", "\t", "\r", "\r"])

    # Then: the completed entity is returned
    assert result == [ALICE]


def test_pick_several():
    # Given/When: the user picks two different entities in sequence
    result = _run(["ali", "\t", "\r", "acme", "\t", "\r", "\r"])

    # Then: both are returned, in selection order
    assert result == [ALICE, ACME]


def test_empty_line_finishes_immediately():
    # Given/When: the user submits an empty line as their first input
    result = _run(["\r"])

    # Then: nothing was picked
    assert result == []


def test_no_match_reprompts_without_losing_prior_picks():
    # Given: the user already picked Alice
    # When: they then type a query matching nothing, and finally pick Acme
    result = _run(["ali", "\t", "\r", "zzz", "\r", "acme", "\t", "\r", "\r"])

    # Then: the no-match submission was ignored and both real picks survived
    assert result == [ALICE, ACME]


def test_duplicate_selection_is_a_no_op():
    # Given/When: the user picks Alice twice
    result = _run(["ali", "\t", "\r", "ali", "\t", "\r", "\r"])

    # Then: Alice only appears once in the result
    assert result == [ALICE]


def test_eof_ends_loop_like_empty_line():
    # Given: the user picks Alice, then closes the input (Ctrl-D / EOF)
    # instead of submitting an empty line
    def _run_eof():
        with create_pipe_input() as pipe_input:
            pipe_input.send_text("ali")
            pipe_input.send_text("\t")
            pipe_input.send_text("\r")
            pipe_input.close()
            picker = PromptToolkitEntityPicker(input=pipe_input, output=DummyOutput())
            return picker.pick(_search)

    # When/Then: the loop ends normally, returning what was picked so far
    result = _run_eof()
    assert result == [ALICE]


def test_ctrl_c_raises_aborted_error():
    # Given/When: the user aborts with Ctrl-C mid-session
    with pytest.raises(EntityPickerAbortedError):
        _run(["ali", "\x03"])
