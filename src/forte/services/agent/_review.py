"""The reviewer seam: the pipeline's only approval surface.

The agent pipeline (extract -> review -> link/create -> review -> field-extract
-> review -> commit) never talks to Click or Rich directly. Instead every
review point in the pipeline hands a batch of :class:`~forte.services.
pipeline_models.ProposedChange` objects to a :class:`Reviewer` and gets back
one :class:`~forte.services.agent._pipeline_models.Decision` per change, in order.

This module intentionally has NO Click and NO Rich imports. Presentation
concerns -- showing one change at a time, rendering the supporting quote or
excerpt, prompting a human, rendering an "Approve" button in a future web
UI -- belong entirely to concrete `Reviewer` implementations. The pipeline
and orchestrator only ever depend on the `Reviewer` protocol defined here, so
a future `WebReviewer` (driven by an HTTP request/response cycle instead of a
terminal) can be dropped in unchanged, with zero changes to the pipeline.

The concrete interactive Rich TUI reviewer used by the CLI is a separate
module/task and is NOT implemented here.

``--dry-run`` semantics (documented here because it's easy to conflate with
review):

- ``--dry-run`` is NOT a reviewer concern. It is an orchestrator-level flag
  meaning "produce (and review) proposals, but skip the commit step
  entirely -- write nothing to markdown or SQLite". The reviewer used during
  a dry run can be any `Reviewer` implementation (interactive, auto-approve,
  scripted); reviewing and committing are separate phases.
- ``--yes`` and ``--dry-run`` COMPOSE: ``--yes`` selects `AutoApproveReviewer`
  (every proposed change is approved without prompting); `--dry-run` then
  still suppresses the commit step. So `--yes --dry-run` means "auto-approve
  everything, then don't write anything" -- useful for previewing what a full
  run would do.
"""

from __future__ import annotations

import typing
from collections.abc import Callable, Sequence

from ._pipeline_models import Decision, ProposedChange


class Reviewer(typing.Protocol):
    """The pipeline's only approval surface.

    Implementations decide how (and whether) to present each proposed change
    to a human or other approver. The pipeline only ever calls `review` and
    only ever consumes the returned `Decision` list -- it has no knowledge of
    how those decisions were made.
    """

    def review(self, changes: list[ProposedChange]) -> list[Decision]:
        """Return one Decision per input change, in the same order."""
        ...


class AutoApproveReviewer:
    """Approves every proposed change without prompting.

    Backs the `--yes` CLI flag: every change handed to `review` comes back
    approved, in the same order, with no user interaction.
    """

    def review(self, changes: list[ProposedChange]) -> list[Decision]:
        return [Decision(change=c, approved=True) for c in changes]


class ScriptedReviewer:
    """Test helper: approves/rejects changes per a scripted predicate or list.

    Construct with either:
    - a predicate `Callable[[ProposedChange], bool]` applied to each change, or
    - a list/sequence of bools, one per expected change (consumed positionally,
      in the order `review` is called).

    Used by other agents' tests to script mixed approve/reject scenarios
    without needing a real interactive reviewer.
    """

    def __init__(self, decisions: Callable[[ProposedChange], bool] | Sequence[bool]):
        self._predicate: Callable[[ProposedChange], bool] | None
        self._bools: list[bool] | None
        if callable(decisions):
            self._predicate = decisions
            self._bools = None
        else:
            self._predicate = None
            self._bools = list(decisions)

    def review(self, changes: list[ProposedChange]) -> list[Decision]:
        if self._predicate is not None:
            return [Decision(change=c, approved=self._predicate(c)) for c in changes]

        bools = self._bools
        assert bools is not None
        if len(bools) < len(changes):
            raise ValueError(
                f"ScriptedReviewer given {len(bools)} bools but asked to review "
                f"{len(changes)} changes"
            )
        return [
            Decision(change=c, approved=approved) for c, approved in zip(changes, bools)
        ]
