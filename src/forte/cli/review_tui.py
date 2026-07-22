"""Interactive Click-based reviewer for the agent pipeline.

This is the ONE place in the CLI where interactive prompting for proposed
changes happens. It implements the `Reviewer` protocol
(`forte.services.agent.Reviewer`) so the pipeline itself never imports
`click` -- see `forte/services/agent/_review.py` for the seam this fills.

The existing Forte CLI is built entirely on `click` (`click.echo` /
`click.confirm`); Rich is not a dependency of this project. To stay
consistent with the rest of the CLI and avoid adding a new dependency, this
reviewer is implemented with plain `click` primitives rather than Rich.
"""

from __future__ import annotations

import click

from forte.services.agent import (
    Decision,
    ProposedChange,
    ProposedFieldSet,
    ProposedLink,
    ProposedNewEntity,
)


class InteractiveReviewer:
    """Presents proposed changes to the user one at a time via the terminal.

    For each change: renders a legible description of the change (including
    the supporting quote, when present) via `click.echo`, then prompts
    `click.confirm("Approve?", default=True)`. Only two actions are
    supported -- approve or reject. There is no inline editing; corrections
    to committed data happen later via `forte entity edit`.
    """

    def review(self, changes: list[ProposedChange]) -> list[Decision]:
        decisions: list[Decision] = []
        for change in changes:
            self._render(change)
            approved = click.confirm("Approve?", default=True)
            decisions.append(Decision(change=change, approved=approved))
        return decisions

    def _render(self, change: ProposedChange) -> None:
        if isinstance(change, ProposedNewEntity):
            self._render_new_entity(change)
        elif isinstance(change, ProposedLink):
            self._render_link(change)
        elif isinstance(change, ProposedFieldSet):
            self._render_field_set(change)
        else:  # pragma: no cover - exhaustiveness guard
            raise TypeError(f"Unknown proposed change type: {type(change)!r}")

    def _render_new_entity(self, change: ProposedNewEntity) -> None:
        click.echo(f"New {change.schema} entity: {change.name}")
        if change.aliases:
            click.echo(f"  aliases: {', '.join(change.aliases)}")
        if change.fields:
            fields_str = ", ".join(f"{k}={v}" for k, v in change.fields.items())
            click.echo(f"  fields: {fields_str}")
        self._render_quote(change.supporting_quote)

    def _render_link(self, change: ProposedLink) -> None:
        click.echo(
            f"Link '{change.candidate_name}' -> existing {change.schema} "
            f"#{change.entity_id} ({change.entity_name})"
        )
        self._render_quote(change.supporting_quote)

    def _render_field_set(self, change: ProposedFieldSet) -> None:
        target = change.target
        fields_str = ", ".join(f"{k}={v}" for k, v in change.fields.items())
        click.echo(f"Set fields on {target.schema} '{target.name}': {fields_str}")

    def _render_quote(self, quote: str) -> None:
        if quote:
            click.echo(f'  quote: "{quote}"')
