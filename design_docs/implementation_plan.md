# Implementation Plan

This file is the task source of truth for planned project work.

Before starting a new change, add one `NEW` task under `Tasks`. The shared state
transitions, commit contract, handoff procedures, review-document format, and
verification workflow are defined in `design_docs/agent_workflow.md`; role
responsibilities are defined in `docs/roles.md`.

## Tasks

## TASK-002 - Build the initial interactive Orc orchestrator

State: COMPLETED

Goal:
- Provide the first usable Orc runtime for coordinating one Igor
  implementation turn and one Rufus review turn in a single terminal.

Dependencies:
- Python 3.11 or newer on POSIX.
- `pyte`, `rich`, and `textual`, declared in `orc.py`'s inline metadata.
- The Codex executable available as `codex` or through `--codex`.

Scope:
- Add `orc.py` with `begin`, `resume`, and idle-hook subcommands.
- Persist task state, role session IDs, user requests, idle events, and
  handoff metadata in `~/.orc/codex-state.json` by default.
- Launch Igor and Rufus in separate private PTYs without `-p`, preserving
  interactive user intervention and hook-driven role transitions.
- Render both sessions in an internal Textual/pyte/Rich TUI with responsive
  side-by-side, stacked, and active-pane-only layouts.
- Forward keyboard input and paste, support pane focus switching, preserve
  terminal colors, and show task/version/status information in the bar.
- Run one Igor turn followed by one Rufus turn, then pause for `resume`.
- Capture each idle handoff's final response with UTC/local timestamps, role,
  task, round, thread ID, and current commit hash.

Acceptance criteria:
- `begin` and `resume` create or continue the correct role sessions and
  preserve task state across process restarts.
- Igor becoming idle starts Rufus; Rufus becoming idle pauses the task.
- The TUI keeps the shell terminal isolated and provides usable PTY input,
  color output, resizing, and active-pane focus.
- Handoff records identify who acted, when, in which task/round, against
  which thread and commit, and retain the agent's final response.
- `orc.py` passes syntax, CLI help, color-render, and diff-integrity checks.

Verification performed:
- `uv run --script orc.py --help`
- `uv run ... python -m py_compile orc.py`
- PTY smoke tests with a harmless child process.
- Hook/state transition simulations and Rich color-render checks.

## TASK-001 - Strip copied Stay foundation for Orc

State: COMPLETED

Completion note: TASK-001 was the bootstrap foundation for Orc. The review
observed `orc.py` before TASK-002 had been committed; that was the intentional
transition into Orc's self-development loop, not unfinished TASK-001 work.

Goal:
- Leave a minimal repository foundation for Orc by removing the copied Stay
  application and its Rust, tmux, packaging, release, formatting, linting, and
  product-documentation artifacts.

Dependencies:
- None.

Scope:
- Remove the Rust application and Rust/tmux tests under `src/` and `tests/`.
- Remove Cargo, Rust toolchain, Nix, tmux acceptance, release, and CI files.
- Remove copied Stay product documentation, external reviews, and formatting
  and linting configuration and scripts.
- Retain and rewrite the agent workflow, roles, known-issues, and
  implementation-plan documents as Orc repository guidance for its future
  self-development loop; remove the inherited lessons document.
- Update repository ignore rules and agent command configuration for the
  Python-oriented Orc foundation.

Acceptance criteria:
- No retained repository file contains the copied Stay Rust or tmux
  application, tests, packaging, release, formatting, or linting setup.
- The retained workflow documents describe Orc generically and do not require
  Cargo, Rust, tmux, Nix, or the removed quality gates.
- `implementation_plan.md` remains the source of truth and this task is marked
  `IMPLEMENTED` only after the conversion is complete.
- Verification confirms no Rust/tmux/Stay references remain outside historical
  Git metadata and this task's conversion record.
