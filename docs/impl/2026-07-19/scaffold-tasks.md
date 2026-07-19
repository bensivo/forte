# Scaffold Application - Tasks

Feature: Set up general application structure per solution-design.md. End state: a runnable CLI that prints `hello-world`.

- Initialize Python project with uv
- Establish four-layer package structure
- Wire up Click CLI entry point with hello-world command
- Configure linting and formatting
- Set up integration test harness
- Add README with dev/run instructions

---

Task: Initialize Python project with uv
ACs:
- A `pyproject.toml` exists at repo root declaring Python 3.11+ and project name `forte`.
- `uv sync` creates a working virtualenv with no errors.
- `.python-version` (or equivalent) pins the interpreter.
- `.gitignore` excludes `.venv/`, `__pycache__/`, `*.egg-info`, `dist/`, `.forte/` (for local test vaults).
Implementation Notes:
- Solution design specifies `uv` for dependency management, virtualenv, and distribution.
- Use `uv init` to bootstrap, then edit `pyproject.toml` as needed.
- Declare Click as first runtime dependency; other deps (anthropic, rich, pypdf, python-docx, python-markdown) can be added as later tasks need them.
- Configure `[project.scripts]` so `forte = "forte.cli:main"` produces the CLI entry point via `uv tool install`.

Task: Establish four-layer package structure
ACs:
- Source lives under `src/forte/` (src layout).
- Four subpackages exist, each with an `__init__.py`: `forte/cli/` (driver), `forte/services/`, `forte/db/`, `forte/domain/`.
- Each layer's `__init__.py` has a one-line docstring naming the layer.
- Importing `forte` succeeds with no side effects.
Implementation Notes:
- Solution design mandates four layers with strict downward-only dependencies: driver → service → db → domain.
- Keep files empty/minimal at this stage — later tasks will populate them.
- Do not create shared "utils" or "common" packages; wait until a real need appears.

Task: Wire up Click CLI entry point with hello-world command
ACs:
- Running `uv run forte` (or `forte` after `uv tool install .`) prints `hello-world` and exits 0.
- The command is defined as a Click group in `forte/cli/__init__.py` (or `forte/cli/main.py`), with `main` as the exported entry point matching `pyproject.toml`.
- A default command or the group's callback produces the `hello-world` output so the bare `forte` invocation works.
- `forte --help` renders without error.
Implementation Notes:
- Use `click.Group` so future subcommand groups (`schema`, `entity`, `doc`) can be attached in later tasks.
- The hello-world behavior is a temporary placeholder — future tasks will replace it with real subcommands per the CLI spec in solution-design.md.
- Keep the CLI module in the driver layer; do not put business logic here.

Task: Configure linting and formatting
ACs:
- `ruff` is configured in `pyproject.toml` for both linting and formatting.
- `uv run ruff check .` and `uv run ruff format --check .` both pass on the scaffolded code.
- Line length and rule set are sensible defaults (e.g. line length 100, default ruff rules plus `I` for import sorting).
Implementation Notes:
- Ruff covers both roles (replaces black + isort + flake8) with one dependency.
- Add as a dev dependency group in `pyproject.toml` (`[dependency-groups] dev = ["ruff"]`).

Task: Set up integration test harness
ACs:
- `pytest` is configured as the test runner in `pyproject.toml`.
- A `tests/` directory exists with a single passing smoke test that invokes the CLI via Click's `CliRunner` and asserts on `hello-world` output.
- `uv run pytest` runs green.
Implementation Notes:
- Solution design calls out an integration-first testing approach driving the real CLI — use `click.testing.CliRunner` from the start so the same pattern extends to future commands.
- Add `pytest` under the `dev` dependency group.
- No LLM stub boundary is needed yet; that comes with the ingest pipeline tasks.

Task: Add README with dev/run instructions
ACs:
- `README.md` at repo root explains: prerequisites (uv, Python 3.11+), how to install (`uv sync`), how to run the CLI (`uv run forte`), how to run tests (`uv run pytest`), and how to lint (`uv run ruff check .`).
- README states the project's one-line purpose and links to `docs/prd.md` and `docs/solution-design.md`.
Implementation Notes:
- Keep it short — this README exists to unblock a new contributor (or agent) in the scaffold phase; product-facing docs live in `docs/`.
