# Implementation Plan

This file is the task source of truth for planned project work.

Before starting a new change, add one `NEW` task under `Tasks`. The shared state
transitions, commit contract, handoff procedures, review-document format, and
verification workflow are defined in `design_docs/agent_workflow.md`; role
responsibilities are defined in `docs/roles.md`.

## Tasks

## TASK-001 - Strip copied Stay foundation for Orc

State: REVIEWED_FOUND_ISSUES

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
