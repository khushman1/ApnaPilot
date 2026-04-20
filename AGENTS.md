# Repository Guidelines

## Project Structure & Module Organization

Core code lives under `src/applypilot/`. Keep CLI wiring in `cli.py`, shared config/bootstrap in `config.py` and
`database.py`, and stage logic in the package folders: `discovery/`, `enrichment/`, `scoring/`, `apply/`, and
`wizard/`. Shipped YAML defaults live in `src/applypilot/config/`. Top-level docs and release notes live in
`README.md`, `CONTRIBUTING.md`, and `CHANGELOG.md`. There is no committed `tests/` directory yet; add new tests under
`tests/` when introducing coverage.

## Build, Test, and Development Commands

Use Python 3.11+.

- `pip install -e ".[dev]"` installs the package in editable mode with `pytest` and `ruff`.
- `playwright install chromium` downloads the browser runtime used by auto-apply flows.
- `applypilot init` creates local profile, search, and environment files.
- `applypilot doctor` validates local prerequisites and missing integrations.
- `applypilot run` executes the pipeline; `applypilot run --workers 4` parallelizes discovery/enrichment.
- `applypilot apply --dry-run` exercises browser automation without submitting applications.
- `ruff check src` runs lint checks; `ruff format src` applies formatting.
- `pytest` runs the test suite once `tests/` exists.

## Coding Style & Naming Conventions

Follow modern Python conventions: 4-space indentation, type hints on public APIs, and short docstrings where behavior
is not obvious. Use `snake_case` for functions, variables, and modules; `PascalCase` for classes; keep CLI option names
consistent with existing Typer commands. Ruff is the only configured style tool, with a `120` character line limit from
`pyproject.toml`.

## Testing Guidelines

Prefer `pytest` for all new coverage. Add focused unit tests beside the feature area, for example
`tests/test_scoring_validator.py` for `src/applypilot/scoring/validator.py`. Cover CLI edge cases, config loading, and
stage-specific regressions. For automation changes, pair code changes with a dry-run path or a small regression test.

## Commit & Pull Request Guidelines

Recent history uses short, imperative subjects such as `Fix setup, Gemini rate limits...`, `Add disclaimer...`, and
`Bump version to 0.3.0`. Keep commits focused and descriptive. PRs should explain the user-visible change, link the
relevant issue when applicable, note any config or dependency changes, and update `CHANGELOG.md` for behavior changes.
Include screenshots or terminal output when changing dashboard, CLI, or browser-driven apply flows.

## Configuration & Safety

Do not commit live secrets. Start from `.env.example` and `profile.example.json`, and keep local credentials in `.env`.
Treat changes to employer/site YAML files as user-facing behavior changes and verify them with a targeted command before
opening a PR.
