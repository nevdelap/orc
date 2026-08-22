# Implementation Plan

This file is the task source of truth for planned project work.

Before starting a new change, add one `NEW` task under `Tasks`. The shared state
transitions, commit contract, handoff procedures, review-document format, and
verification workflow are defined in `design_docs/agent_workflow.md`; role
responsibilities are defined in `docs/roles.md`.

## Tasks

## TASK-003 - Run Orc against a target project directory

State: COMPLETED

Goal:

- Allow Orc to orchestrate Igor and Rufus for a project other than Orc's own
  repository by selecting and retaining an explicit target directory.

Dependencies:

- None.

Scope:

- `orc.py`: CLI parsing, task-state persistence, child launch, idle-hook
  lookup, target-directory handling, and target Git evidence.
- `README.md`: the complete user-facing tool guide described below.
- `tests/` and test fixtures: comprehensive Python coverage for CLI argument
  validation, state persistence, child working directory, resume safety,
  target commit capture, PTY/TUI behavior, ANSI rendering, input forwarding,
  resize handling, role transitions, and handoff metadata.
- `.github/workflows/ci.yml`: CI on Ubuntu 24.04 for Python 3.11, 3.12, 3.13,
  and 3.14, with a matrix test job and dedicated quality, integration,
  documentation, and dependency/security jobs.
- `.github/dependabot.yml`, `pyproject.toml`, and `uv.lock`: dependency,
  test-tool, and CI configuration required by those jobs.
- `.gitignore`: only if needed for generated test, coverage, or diagnostic
  artifacts.
- Validate and normalize the target as an existing directory before creating
  or launching a task.
- Persist the normalized target directory in the task record and require a
  resume directory to match the stored target.
- Launch every Igor and Rufus Codex child with the target directory as its
  working directory, while keeping Orc's own state file and UI process outside
  that directory.
- Ensure role prompts, idle-hook lookup, current-commit handoffs, and review
  evidence refer to the target project's directory and Git repository.
- Create a complete user-facing `README.md` covering Orc's purpose,
  prerequisites, installation or launch method, state location, the Igor and
  Rufus workflow, interaction model, troubleshooting, and positional
  `begin DIRECTORY TASK-ID PROMPT` and `resume DIRECTORY TASK-ID PROMPT` usage
  examples.
- Update CLI help, task state, and documentation without changing the existing
  TUI interaction model.

Acceptance criteria:

- `begin DIRECTORY TASK-ID PROMPT` validates the positional directory, stores
  its normalized value, and launches both roles there.
- `resume DIRECTORY TASK-ID PROMPT` requires a directory matching the stored
  target and rejects a conflicting directory before launching a child.
- A target outside `/workspace` can be implemented and reviewed without Orc
  reading or committing against Orc's repository by accident.
- Handoff commit hashes and review evidence are collected from the target
  repository, while Orc state remains in the configured Orc state file.
- Invalid, missing, and non-directory paths fail with clear CLI errors and do
  not create a task record or mutate an existing task's directory.
- The CLI help and errors clearly describe the required positional directory.
- `README.md` is a complete, accurate user guide for running Orc against a
  target project, including the target-directory model and both command forms
  with examples that match the implemented CLI.
- The test suite covers CLI help and errors, argument/state behavior, child
  CWD, resume persistence, target-repository commit capture, PTY/TUI behavior,
  role transitions, handoffs, colors, input, and resizing.
- CI runs on Ubuntu 24.04 with Python 3.11, 3.12, 3.13, and 3.14. It runs
  these exact checks: `uv sync --locked`; `uv run pytest -q --cov=orc --cov-report=term-missing --cov-fail-under=90`; `uv run ruff check .`;
  `uv run ruff format --check .`; `uv run mypy orc.py`;
  `uv run python -m compileall -q orc.py tests`; `uv run mdformat --check README.md design_docs docs`; `uv run pip-audit --strict`; and
  `actionlint .github/workflows/ci.yml`.
- CI includes the full PTY/integration suite, uploads useful failure
  diagnostics, and fails on any check failure.
- Verification covers the same checks locally where possible, plus syntax and
  clean diff integrity.
