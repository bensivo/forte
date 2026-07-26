"""Tests for the bulk-commit editor document format (render/parse)."""

from __future__ import annotations

from forte.services.agent._bulk_format import parse, render
from forte.services.agent._pipeline_models import (
    Decision,
    FieldSetTarget,
    ProposedFieldSet,
    ProposedLink,
    ProposedNewEntity,
)


def _new_entity(name="Alice", **kwargs):
    defaults = dict(name=name, schema="person", supporting_quote=f"{name} said hi.")
    defaults.update(kwargs)
    return ProposedNewEntity(**defaults)


def _link(candidate_name="Bob", entity_id=1, entity_name="Bob Smith", **kwargs):
    defaults = dict(
        entity_id=entity_id,
        entity_name=entity_name,
        schema="person",
        candidate_name=candidate_name,
        supporting_quote=f"{candidate_name} works here.",
    )
    defaults.update(kwargs)
    return ProposedLink(**defaults)


def _field_set(name="Alice", entity_id=1, new_entity_ref=None, fields=None, **kwargs):
    target = FieldSetTarget(
        name=name,
        schema="person",
        entity_id=entity_id if new_entity_ref is None else None,
        new_entity_ref=new_entity_ref,
    )
    defaults = dict(target=target, fields=fields or {"role": "engineer"}, source_doc_id=1)
    defaults.update(kwargs)
    return ProposedFieldSet(**defaults)


# --- render: structure and content ------------------------------------------------


def test_render_includes_header_and_sections():
    changes = [_new_entity()]
    text = render(changes)

    assert "## New entities" in text
    assert "## Links to existing entities" in text
    assert "## Field updates" in text
    # Header documents the [y]/[n] scheme, not the raw sketch's [n]/[s]/[l].
    assert "[y]" in text
    assert "[n]" in text
    assert "[s]" not in text
    assert "[l]" not in text
    assert "deleted" in text.lower()
    assert "cannot add" in text.lower() or "cannot" in text.lower()


def test_render_empty_sections_show_none_placeholder():
    text = render([_new_entity()])

    # Only the "New entities" section has content; the other two are empty.
    links_section = text.split("## Links to existing entities")[1].split(
        "## Field updates"
    )[0]
    fields_section = text.split("## Field updates")[1]
    assert "(none" in links_section
    assert "(none" in fields_section


def test_render_new_entity_line_format_and_change_id():
    change = _new_entity(name="Alice", aliases=["Al"], fields={"role": "engineer"})
    text = render([change])

    assert "[y] c0  New person entity: Alice" in text
    assert "Al" in text
    assert "role=engineer" in text
    assert '"Alice said hi."' in text


def test_render_link_line_format():
    change = _link(candidate_name="Bob", entity_id=42, entity_name="Bob Smith")
    text = render([change])

    assert "[y] c0" in text
    assert "Bob" in text
    assert "#42" in text
    assert "Bob Smith" in text
    assert "existing person" in text


def test_render_field_set_line_format():
    change = _field_set(name="Alice", entity_id=1, fields={"role": "engineer", "team": "x"})
    text = render([change])

    assert "[y] c0" in text
    assert "Set fields on person 'Alice'" in text
    assert "role=engineer" in text
    assert "team=x" in text


def test_render_all_three_kinds_land_in_correct_sections():
    new_entity = _new_entity(name="Alice")
    link = _link(candidate_name="Bob")
    field_set = _field_set(name="Charlie", entity_id=3)
    text = render([new_entity, link, field_set])

    header, rest = text.split("## New entities", 1)
    new_section, rest = rest.split("## Links to existing entities", 1)
    link_section, field_section = rest.split("## Field updates", 1)

    assert "Alice" in new_section
    assert "Bob" not in new_section
    assert "Charlie" not in new_section

    assert "Bob" in link_section
    assert "Alice" not in link_section
    assert "Charlie" not in link_section

    assert "Charlie" in field_section
    assert "Alice" not in field_section
    assert "Bob" not in field_section

    # change-ids are assigned by global index into `changes`, not per-section.
    assert "c0" in new_section
    assert "c1" in link_section
    assert "c2" in field_section


def test_render_change_ids_assigned_by_global_index():
    changes = [_new_entity(name="A"), _new_entity(name="B"), _link(candidate_name="C")]
    text = render(changes)

    assert "[y] c0  New person entity: A" in text
    assert "[y] c1  New person entity: B" in text
    assert "[y] c2" in text and "C" in text


# --- parse: round trip and mutation behaviors --------------------------------------


def test_parse_no_edits_all_approved():
    changes = [_new_entity(), _link(), _field_set()]
    text = render(changes)

    decisions = parse(text, changes)

    assert decisions == [Decision(change=c, approved=True) for c in changes]


def test_parse_flip_to_n_rejects_that_change_only():
    changes = [_new_entity(name="Alice"), _new_entity(name="Bob")]
    text = render(changes)
    edited = text.replace("[y] c1", "[n] c1")

    decisions = parse(edited, changes)

    assert decisions[0] == Decision(change=changes[0], approved=True)
    assert decisions[1] == Decision(change=changes[1], approved=False)


def test_parse_deleted_line_is_rejected():
    changes = [_new_entity(name="Alice"), _new_entity(name="Bob")]
    text = render(changes)

    edited_lines = [
        line for line in text.splitlines() if "c1" not in line
    ]
    edited = "\n".join(edited_lines)

    decisions = parse(edited, changes)

    assert decisions[0] == Decision(change=changes[0], approved=True)
    assert decisions[1] == Decision(change=changes[1], approved=False)


def test_parse_garbage_action_is_rejected():
    changes = [_new_entity(name="Alice")]
    text = render(changes)
    edited = text.replace("[y] c0", "[x] c0")

    decisions = parse(edited, changes)

    assert decisions == [Decision(change=changes[0], approved=False)]


def test_parse_blank_action_is_rejected():
    changes = [_new_entity(name="Alice")]
    text = render(changes)
    edited = text.replace("[y] c0", "[] c0")

    decisions = parse(edited, changes)

    assert decisions == [Decision(change=changes[0], approved=False)]


def test_parse_reordering_lines_preserves_mapping():
    changes = [_new_entity(name="Alice"), _new_entity(name="Bob"), _new_entity(name="Charlie")]
    text = render(changes)
    edited = text.replace("[y] c0", "[n] c0")

    lines = edited.splitlines()
    # Find and reorder the three proposal lines (c0, c1, c2) within the doc,
    # simulating a user cutting/pasting lines around.
    proposal_lines = [
        line
        for line in lines
        if any(f" c{i}" in line and line.strip().startswith("[") for i in range(3))
    ]
    shuffled = list(reversed(proposal_lines))
    # Reinsert shuffled proposal lines where the originals were, in order encountered.
    result_lines = []
    shuffled_iter = iter(shuffled)
    for line in lines:
        if line in proposal_lines:
            result_lines.append(next(shuffled_iter))
        else:
            result_lines.append(line)
    reordered = "\n".join(result_lines)

    decisions = parse(reordered, changes)

    assert decisions[0] == Decision(change=changes[0], approved=False)
    assert decisions[1] == Decision(change=changes[1], approved=True)
    assert decisions[2] == Decision(change=changes[2], approved=True)


def test_parse_full_line_reorder_across_document():
    """Cutting a proposal line out of its section and pasting it elsewhere
    in the document still maps it back to the correct change."""
    changes = [_new_entity(name="Alice"), _link(candidate_name="Bob")]
    text = render(changes)
    edited = text.replace("[y] c1", "[n] c1")

    lines = edited.splitlines()
    c1_line = next(line for line in lines if line.strip().startswith("[") and " c1 " in line)
    lines.remove(c1_line)
    # Move it to the very top of the document.
    reordered = "\n".join([c1_line, *lines])

    decisions = parse(reordered, changes)

    assert decisions[0] == Decision(change=changes[0], approved=True)
    assert decisions[1] == Decision(change=changes[1], approved=False)


def test_parse_ignores_comment_and_section_and_header_lines():
    changes = [_new_entity(name="Alice", aliases=["Al"], fields={"role": "eng"})]
    text = render(changes)

    # Sanity: comment/header/section lines exist and don't accidentally
    # introduce spurious change-ids.
    decisions = parse(text, changes)
    assert decisions == [Decision(change=changes[0], approved=True)]


def test_parse_link_display_id_is_not_used_as_parse_key():
    """The '#<entity_id>' shown on link lines is display-only; mangling it
    must not affect the decision, since the change-id token is what's keyed
    on, not the entity id."""
    changes = [_link(candidate_name="Bob", entity_id=99, entity_name="Bob Smith")]
    text = render(changes)
    # Corrupt the displayed entity id / name but keep [y] c0 intact.
    mangled = text.replace("#99", "#1").replace("Bob Smith", "Someone Else")

    decisions = parse(mangled, changes)

    assert decisions == [Decision(change=changes[0], approved=True)]


def test_parse_extra_unknown_change_id_in_text_is_harmless():
    changes = [_new_entity(name="Alice")]
    text = render(changes)
    edited = text + "\n[y] c99  Some phantom line\n"

    decisions = parse(edited, changes)

    assert decisions == [Decision(change=changes[0], approved=True)]


def test_render_parse_round_trip_mixed_kinds():
    new_entity = _new_entity(name="Alice")
    link = _link(candidate_name="Bob", entity_id=5, entity_name="Bob Smith")
    field_set_existing = _field_set(name="Charlie", entity_id=3, fields={"team": "x"})
    field_set_new = _field_set(
        name="Alice", entity_id=None, new_entity_ref=0, fields={"role": "eng"}
    )
    changes = [new_entity, link, field_set_existing, field_set_new]

    text = render(changes)
    # Reject the link (c1) and the field set on the existing entity (c2).
    edited = text.replace("[y] c1", "[n] c1").replace("[y] c2", "[n] c2")

    decisions = parse(edited, changes)

    assert decisions[0] == Decision(change=new_entity, approved=True)
    assert decisions[1] == Decision(change=link, approved=False)
    assert decisions[2] == Decision(change=field_set_existing, approved=False)
    assert decisions[3] == Decision(change=field_set_new, approved=True)


def test_render_empty_changes_list():
    text = render([])

    assert "## New entities" in text
    assert "## Links to existing entities" in text
    assert "## Field updates" in text
    assert parse(text, []) == []


# --- parse: renaming new entities --------------------------------------------------


def test_parse_rename_new_entity_returns_renamed_copy():
    change = _new_entity(name="Alice")
    text = render([change])
    edited = text.replace("entity: Alice", "entity: Alicia Renamed")

    decisions = parse(edited, [change])

    assert decisions[0].approved is True
    assert decisions[0].change.name == "Alicia Renamed"
    # Original proposal is left untouched (replace returns a copy).
    assert change.name == "Alice"
    # Other fields carried over unchanged.
    assert decisions[0].change.schema == change.schema
    assert decisions[0].change.supporting_quote == change.supporting_quote


def test_parse_rename_preserves_aliases_and_fields():
    change = _new_entity(name="Alice", aliases=["Al"], fields={"role": "eng"})
    text = render([change])
    edited = text.replace("entity: Alice", "entity: Alicia")

    renamed = parse(edited, [change])[0].change

    assert renamed.name == "Alicia"
    assert renamed.aliases == ["Al"]
    assert renamed.fields == {"role": "eng"}


def test_parse_rename_can_combine_with_rejection():
    change = _new_entity(name="Alice")
    text = render([change])
    edited = text.replace("[y] c0  New person entity: Alice", "[n] c0  New person entity: Alicia")

    decision = parse(edited, [change])[0]

    # Renamed on the change even though it was rejected — the orchestrator
    # decides whether the (renamed) proposal is created (e.g. via promotion).
    assert decision.approved is False
    assert decision.change.name == "Alicia"


def test_parse_unchanged_name_returns_same_object():
    change = _new_entity(name="Alice")
    text = render([change])

    decision = parse(text, [change])[0]

    assert decision.change is change  # no copy made when nothing was renamed


def test_parse_blanked_name_keeps_original():
    change = _new_entity(name="Alice")
    text = render([change])
    edited = text.replace("entity: Alice", "entity:")

    decision = parse(edited, [change])[0]

    assert decision.change.name == "Alice"


def test_parse_rename_only_applies_to_new_entities_not_links():
    link = _link(candidate_name="Bob", entity_id=5, entity_name="Bob Smith")
    text = render([link])
    # Editing the link's display text must not rename anything.
    edited = text.replace("Bob Smith", "Robert Smith")

    decision = parse(edited, [link])[0]

    assert decision.change is link
