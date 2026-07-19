"""Unit tests for entity markdown (frontmatter) serialization — pure, no I/O."""

from __future__ import annotations

import pytest

from forte.domain.entity import Entity
from forte.domain.entity_markdown import (
    ParsedEntity,
    from_markdown,
    slugify,
    to_markdown,
)


def test_round_trip_recovers_name_aliases_fields_and_body() -> None:
    entity = Entity(
        schema="person",
        name="Ben Sivongxay",
        aliases=["Ben", "Ben S."],
        fields={"employer": "Acme", "role": "Engineer", "city": "Seattle"},
        body="Some free-form notes.\n\nA second paragraph.",
    )

    parsed = from_markdown(to_markdown(entity))

    assert parsed == ParsedEntity(
        name="Ben Sivongxay",
        aliases=["Ben", "Ben S."],
        fields={"employer": "Acme", "role": "Engineer", "city": "Seattle"},
        body="Some free-form notes.\n\nA second paragraph.",
    )


def test_field_order_is_preserved() -> None:
    entity = Entity(
        schema="person",
        name="Ben",
        fields={"employer": "Acme", "role": "Engineer", "city": "Seattle"},
    )

    parsed = from_markdown(to_markdown(entity))

    assert list(parsed.fields.keys()) == ["employer", "role", "city"]


def test_empty_field_values_render_and_are_not_omitted() -> None:
    entity = Entity(
        schema="person",
        name="Ben",
        fields={"employer": "", "role": ""},
    )

    text = to_markdown(entity)
    # Both keys must still appear in the frontmatter, with empty values.
    assert "employer:" in text
    assert "role:" in text

    parsed = from_markdown(text)
    assert parsed.fields == {"employer": "", "role": ""}


def test_empty_alias_list_round_trips() -> None:
    entity = Entity(schema="person", name="Ben", aliases=[])

    parsed = from_markdown(to_markdown(entity))

    assert parsed.aliases == []


def test_empty_body_round_trips() -> None:
    entity = Entity(schema="person", name="Ben")

    parsed = from_markdown(to_markdown(entity))

    assert parsed.body == ""


def test_values_with_special_characters_round_trip() -> None:
    entity = Entity(
        schema="person",
        name="Renée: the O'Brien",
        aliases=["R.", "the \"boss\""],
        fields={"note": "a: b, c # d", "quote": "he said \"hi\""},
    )

    parsed = from_markdown(to_markdown(entity))

    assert parsed.name == "Renée: the O'Brien"
    assert parsed.aliases == ["R.", "the \"boss\""]
    assert parsed.fields == {"note": "a: b, c # d", "quote": "he said \"hi\""}


def test_from_markdown_requires_frontmatter() -> None:
    with pytest.raises(ValueError):
        from_markdown("just a body, no frontmatter\n")


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Ben Sivongxay", "ben-sivongxay"),
        ("Acme Corp.", "acme-corp"),
        ("  Spaced   Out  ", "spaced-out"),
        ("Weird/Chars*Here?", "weirdcharshere"),
        ("Already-Sluggy_ok", "already-sluggy_ok"),
    ],
)
def test_slugify(name: str, expected: str) -> None:
    assert slugify(name) == expected
