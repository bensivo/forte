# Style Guide

Conventions for how code and docs are organized in this project. Written up as issues arise so the same mistakes don't repeat.

## Layering: keep the CLI dumb

The `src/forte/cli/` package is the **driver layer**. It only:

- Declares Click commands, groups, flags, arguments.
- Parses / validates input from the user.
- Calls a single function in the service layer.
- Formats the result (or exception) for the terminal.

The CLI must contain **no business logic**. Concretely: no path composition, no filesystem side effects, no DB calls, no orchestration of multiple modules. If a command's body is more than "parse → call service → echo result", the logic belongs in a service.

Each user-facing command should map to a single pure-ish service function that takes the parsed inputs and does the work — e.g. `forte init` calls `services.init.init(root: Path)`. This makes the behavior testable without Click, and lets other drivers (a future TUI, an API) reuse the same function.

**Bad:**

```python
@main.command()
def init() -> None:
    layout = VaultLayout(Path.cwd())
    if layout.forte_dir.exists(): raise click.ClickException(...)
    for d in layout.all_dirs(): d.mkdir(parents=True)
    write_default_config(layout.config_path)
    initialize_database(layout.db_path)
```

**Good:**

```python
@main.command()
def init() -> None:
    from forte.services.init import init as init_vault
    root = init_vault(Path.cwd())
    click.echo(f"Initialized Forte vault in {root}")
```

## `docs/spec/` is user-facing behavior only

Files under `docs/spec/` are the source of truth for **integration / end-to-end behavior** — what a user, or another system talking to Forte, observes. They drive integration tests.

They are **not** the place for:

- Specs of internal modules or classes (e.g. "VaultLayout returns these paths").
- Unit-level invariants (purity, immutability, dataclass field lists).
- Anything a caller of the public CLI / API wouldn't care about.

Rule of thumb: if the only way to observe the behavior is by importing an internal Python symbol, it's a unit concern — cover it with a unit test in `tests/`, no spec doc. If the behavior is observable by running `forte …` or hitting a public interface, it belongs in `docs/spec/`.

One file per feature area, Gherkin-style scenarios inside.

## Tests

- Unit tests live in `tests/` alongside integration tests, but they do not need a matching spec doc.
- Integration tests should trace back to a scenario in a `docs/spec/` file.
- Prefer real filesystem / real SQLite (via `tmp_path`) over mocks — mocks that drift from reality cost more than they save.
