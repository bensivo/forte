"""Private internals of :class:`forte.service.agent_service.AgentService`.

The agent pipeline (extract -> review -> link/create -> review -> field-extract
-> review -> commit) is far too large for one module, so its steps live here as
leading-underscore modules: prompt templates (`_prompts`), the bounded-retry
structured-call helper (`_structured`), the three LLM steps (`_steps`), the
orchestrators (`_orchestrator`), the bulk editor document format
(`_bulk_format`), the best-effort committer (`_commit`), the reviewer seam
(`_review`), and cost reporting (`_cost`). The editor seam is NOT one of
these -- it is `forte.interface.editor.IEditor`, a feature-neutral interface,
since the editor is a client dependency the pipeline consumes rather than
something the agent feature owns.

Nothing in this package is public API. Outside code depends on `AgentService`
(and the seam protocols it re-exports) only.
"""
