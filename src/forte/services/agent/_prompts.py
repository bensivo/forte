"""In-source prompt templates + JSON schemas + parse functions for the LLM steps.

This module is the single home for the three LLM prompts the agent pipeline
runs — (1) extract entities, (2) link a candidate among rule-matched existing
entities, (3) extract schema field values — each paired with the JSON schema
the structured-call helper constrains the model to, and a ``parse`` callback
that validates the raw JSON text and RAISES on anything malformed (so
``structured_call`` retries).

The prompts are deliberately kept together, heavily commented, and easy to diff:
prompt quality is the primary lever the team expects to iterate on. All
vault-specific data (the list of schema names, the numbered list of candidate
entities, the entity's declared field names) is injected as DATA via the
``build_*`` helpers, never hardcoded, so every prompt works for any vault.

FUTURE: per-vault prompt overrides are a planned feature — a vault will be able
to supply its own template text that replaces the constants below. For now the
prompts live in source. When that lands, this module is the hook point: read the
override (if any) from the vault config and fall back to these defaults.

Division of responsibility between ``parse`` and the step functions
(``forte.services.agent._steps``):
  - ``parse`` validates SHAPE and hard-invalid values only, and RAISES on
    malformed / missing / wrong-typed JSON, or on an out-of-range link id — all
    of which are worth a retry.
  - Non-error semantic FILTERING (e.g. dropping an extracted candidate whose
    schema does not exist in this vault) is NOT done here; it happens in the
    step after a successful parse, so it never triggers a retry.
"""

from __future__ import annotations

import json

from forte.domain.entity import Entity

from ._pipeline_models import CandidateEntity

# ---------------------------------------------------------------------------
# Step 1: extract entities
# ---------------------------------------------------------------------------

EXTRACTION_SYSTEM = """\
You extract entities from a document for a personal knowledge base.

Rules:
- Be CONSERVATIVE. Only extract things the document actually NAMES or DESCRIBES.
  Do not infer, guess, or invent entities that are merely alluded to.
- Classify each entity into EXACTLY ONE of the schema names provided by the
  user. If a thing does not fit any of the given schemas, DO NOT extract it.
- For every entity you MUST supply a `supporting_quote`: a short verbatim
  excerpt copied from the document that shows where the entity appears. The
  quote is required evidence — never leave it empty and never paraphrase.
- Return each entity as {name, schema, supporting_quote}. `name` is the entity's
  canonical display name as the document refers to it.
- It is perfectly valid to return an empty list when the document names nothing
  that fits the given schemas.
"""

# JSON schema the model is constrained to. Every object carries
# `additionalProperties: false` and an explicit `required` array (Anthropic
# json_schema constraints).
EXTRACTION_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "schema": {"type": "string"},
                    "supporting_quote": {"type": "string"},
                },
                "required": ["name", "schema", "supporting_quote"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["entities"],
    "additionalProperties": False,
}


def build_extraction_user(doc_text: str, schema_names: list[str]) -> str:
    """Render the extract-entities user prompt, injecting the vault's schemas."""
    schema_lines = "\n".join(f"- {name}" for name in schema_names)
    return (
        "Available schema names (classify only into these):\n"
        f"{schema_lines}\n\n"
        "Document:\n"
        "---\n"
        f"{doc_text}\n"
        "---\n\n"
        "Extract the entities this document names or describes."
    )


def parse_extraction(text: str) -> list[CandidateEntity]:
    """Validate the extraction JSON and return candidates; RAISE if malformed.

    Shape validation only: each item must be an object with non-empty string
    ``name``/``schema``/``supporting_quote``. Any deviation raises so the call
    is retried. Candidates whose schema does not exist in the vault are NOT
    dropped here — that non-error filter lives in ``extract_entities``.
    """
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("extraction response must be a JSON object")
    items = data["entities"]  # KeyError -> retry
    if not isinstance(items, list):
        raise ValueError("`entities` must be a list")

    candidates: list[CandidateEntity] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("each entity must be an object")
        name = item["name"]
        schema = item["schema"]
        quote = item["supporting_quote"]
        for value in (name, schema, quote):
            if not isinstance(value, str):
                raise ValueError("name/schema/supporting_quote must be strings")
        if not name.strip() or not schema.strip() or not quote.strip():
            raise ValueError("name/schema/supporting_quote must be non-empty")
        candidates.append(
            CandidateEntity(name=name, schema=schema, supporting_quote=quote)
        )
    return candidates


# ---------------------------------------------------------------------------
# Step 2: link a candidate among rule-matched existing entities (or none)
# ---------------------------------------------------------------------------

LINK_SYSTEM = """\
You decide whether an extracted entity candidate refers to one of a small set
of EXISTING knowledge-base entities, or to none of them.

Rules:
- You are given the candidate, the surrounding document context, and a NUMBERED
  list of existing entities. Each list item shows the entity's real id.
- Return the `entity_id` of the single existing entity the candidate refers to,
  choosing the id EXACTLY as shown in the list. If the candidate refers to none
  of the listed entities, return null.
- NEVER invent an id. You may ONLY return one of the ids shown in the list, or
  null. Returning any other id is a hard error.
- Prefer linking when the candidate clearly refers to a listed entity; return
  null when you are not confident it is any of them.
"""

LINK_SCHEMA: dict = {
    "type": "object",
    "properties": {
        # The chosen existing entity id, or null for "no match".
        "entity_id": {"type": ["integer", "null"]},
    },
    "required": ["entity_id"],
    "additionalProperties": False,
}


def build_link_user(
    candidate: CandidateEntity, doc_text: str, entities: list[Entity]
) -> str:
    """Render the link user prompt with a numbered list of rule-matched entities."""
    lines = []
    for i, entity in enumerate(entities, start=1):
        alias_part = f" (aliases: {', '.join(entity.aliases)})" if entity.aliases else ""
        lines.append(f"{i}. [id={entity.id}] {entity.name}{alias_part} — schema: {entity.schema}")
    entity_list = "\n".join(lines)
    return (
        f"Candidate entity: {candidate.name} (schema: {candidate.schema})\n"
        f"Where it appears: {candidate.supporting_quote}\n\n"
        "Existing entities it might refer to:\n"
        f"{entity_list}\n\n"
        "Document context:\n"
        "---\n"
        f"{doc_text}\n"
        "---\n\n"
        "Return the `entity_id` of the matching existing entity (using its id "
        "exactly as shown above), or null if the candidate matches none of them."
    )


def make_link_parser(allowed_ids: list[int]):
    """Return a ``parse`` callback that validates the link response.

    The returned parser accepts ``{"entity_id": <int|null>}``. ``null`` means
    "no match" and parses to ``None``. An integer id is validated against
    ``allowed_ids`` — an id OUTSIDE that set is a validation failure and RAISES
    (retryable), which is how "the model must never invent an id" is enforced.
    """
    allowed = set(allowed_ids)

    def _parse(text: str) -> int | None:
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("link response must be a JSON object")
        entity_id = data["entity_id"]  # KeyError -> retry
        if entity_id is None:
            return None
        # bool is a subclass of int — reject it explicitly.
        if not isinstance(entity_id, int) or isinstance(entity_id, bool):
            raise ValueError("entity_id must be an integer or null")
        if entity_id not in allowed:
            raise ValueError(f"entity_id {entity_id} is not one of the offered ids")
        return entity_id

    return _parse


# ---------------------------------------------------------------------------
# Step 3: extract schema field values for one entity
# ---------------------------------------------------------------------------

FIELD_SYSTEM = """\
You extract structured field values for ONE knowledge-base entity from a
document.

Rules:
- You are given the entity, its schema, the exact list of fields that schema
  declares, and the document. Return a value ONLY for the declared fields.
- Only provide a value where the DOCUMENT actually supports it. If the document
  does not state a field's value, return an empty string "" for that field.
- Do not invent, guess, or infer values that the document does not support, and
  do not return any field name that is not in the declared list.
- Values are short free-text strings.
"""


def build_field_schema(field_names: list[str]) -> dict:
    """Build the field-extraction JSON schema DYNAMICALLY from declared fields.

    Each declared field becomes a required string property. Requiring every
    field keeps the response shape predictable; "not supported by the document"
    is expressed as an EMPTY STRING (which ``extract_fields`` then drops), rather
    than by omitting the key. Extra/unknown properties are forbidden.
    """
    return {
        "type": "object",
        "properties": {name: {"type": "string"} for name in field_names},
        "required": list(field_names),
        "additionalProperties": False,
    }


def build_field_user(
    name: str, schema_name: str, field_names: list[str], doc_text: str
) -> str:
    """Render the field-extraction user prompt for one entity."""
    field_lines = "\n".join(f"- {field}" for field in field_names)
    return (
        f"Entity: {name} (schema: {schema_name})\n\n"
        "Declared fields to extract (return a value only where the document "
        "supports it, empty string otherwise):\n"
        f"{field_lines}\n\n"
        "Document:\n"
        "---\n"
        f"{doc_text}\n"
        "---\n\n"
        "Return the field values."
    )


def make_field_parser(field_names: list[str]):
    """Return a ``parse`` callback validating the field-extraction response.

    Validates that the response is an object mapping declared field names to
    string values. An UNKNOWN field name (outside ``field_names``) or a
    non-string value RAISES (retryable). Missing declared keys are tolerated
    (treated as empty). The returned dict preserves empty strings; dropping
    empties (the "nothing extractable" filter) happens in ``extract_fields``.
    """
    allowed = set(field_names)

    def _parse(text: str) -> dict[str, str]:
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("field response must be a JSON object")
        result: dict[str, str] = {}
        for key, value in data.items():
            if key not in allowed:
                raise ValueError(f"unknown field: {key}")
            if not isinstance(value, str):
                raise ValueError(f"field {key} must be a string")
            result[key] = value
        return result

    return _parse
