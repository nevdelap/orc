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

## TASK-004 - Fix PTY resizing and pane focus input

State: NEW

Goal:

- Make the Orc UI fully usable for a normal operator from launch through
  shutdown, including reliable panes, resizing, focus, input, status, and
  colors.
- Make Orc's panes and child PTYs follow terminal resizes reliably, while
  removing global shortcuts that can consume input intended for Codex.
- Make `orc.py` directly executable through its `uv` shebang.

Dependencies:

- TASK-003 must be `COMPLETED`.

Scope:

- `orc.py`: Textual resize/layout handling, PTY `TIOCSWINSZ` propagation,
  pane focus, key handling, status text, and executable script metadata.
- `tests/test_orc.py` and PTY/integration fixtures: resize, geometry, focus,
  input forwarding, startup/placeholder states, status rendering, colors,
  and direct-script invocation coverage.
- `README.md`: direct `./orc.py` usage, focus behavior, resize
  troubleshooting, and the complete operator interaction model.
- The operator validation protocol: Igor must ask Nev to manually exercise
  the UI at defined checkpoints as implementation progresses, report the
  exact commit and scenario for each checkpoint, and incorporate feedback
  before requesting review.
- Nev is the human operator and acceptance tester, not an Orc agent role. The
  manual test environment is a Linux terminal with `TERM=xterm-256color`,
  `uv`, and a configured Codex command. The required size matrix is 120x40
  side-by-side, 80x40 stacked, and 80x24 single-pane.
- Manual evidence is recorded in the `Nev validation` section of
  `review_docs/TASK-004.md`, including commit, terminal type, size, command,
  scenario, observation, and pass/fail result.
- Preserve the Linux-only POSIX PTY support model.
- Ensure the first line remains an executable uv shebang in the form
  `#!/usr/bin/env -S uv run --script`, with valid inline script metadata.
- Remove `1`, `2`, `Tab`, and `Shift-Tab` as global pane-switching shortcuts.
- Provide a non-conflicting focus mechanism, such as clicking a pane, with
  visible active-pane feedback.
- Measure each rendered pane and propagate its width and height to its child
  PTY after startup, attach, layout changes, and terminal resize.
- Exercise the complete UI journey: launch/startup messaging, both role panes,
  active/inactive borders, status and version text, color output, normal and
  control-key input, paste, focus selection, resize, handoff transition, and
  Ctrl-Q shutdown.
- At each checkpoint, ask Nev to run the exact documented scenario on the
  current commit: startup at 120x40, focus/input and resize through 80x40 and
  80x24, then handoff and Ctrl-Q shutdown. A failed result is a blocking
  finding; a task cannot be marked complete until every checkpoint is recorded
  as pass or an explicit blocker.

Acceptance criteria:

- `./orc.py --help` runs from an executable checkout without a separate
  `uv run` prefix, and the documented direct invocation works.
- The UI presents useful startup and not-yet-started messages, shows both
  role panes and their states, keeps the active border visibly distinct, and
  displays the task name and Orc version without clipping in supported sizes.
- Nev's three manual checkpoints pass in the specified Linux terminal and
  size matrix, with evidence recorded in `review_docs/TASK-004.md`; Rufus
  independently verifies the evidence and repeats the scenarios as needed.
- A live terminal resize updates both rendered panes and matching child PTYs
  without restarting Orc or Codex.
- Resizes before attach, during startup, after attach, rapid repeated
  resizes, tiny terminals, and both layout modes are handled safely.
- Tests prove PTY dimensions come from the rendered pane rather than a stale
  outer-terminal or initial value.
- No blank, one-column, one-row, or apparently hung pane remains after a
  resize; a Linux PTY test observes correctly redrawn output.
- Pressing `1`, `2`, `Tab`, or `Shift-Tab` does not change the active pane.
- The replacement focus mechanism selects either pane and updates the border
  and status reliably.
- Formerly intercepted Tab and Shift-Tab input reaches the active Codex PTY
  in the form reported by the terminal whenever available.
- README, status text, and tests contain none of the removed shortcuts.
- Existing color, paste, control-key, handoff, completion, and target
  directory behavior remains passing.
- Igor asks Nev to test at the startup, interaction/resize, and end-to-end
  shutdown checkpoints. Each request identifies the tested commit and exact
  scenario; Nev's observations and any fixes are recorded before final review.
- Rufus independently verifies the complete UI journey and confirms that the
  requested Nev checkpoints were performed or records the remaining blocker.
- Applicable project checks, PTY/integration tests, direct-script checks, and
  clean-diff verification pass.

## TASK-005 - Add bounded workflow control and clarification pauses

State: NEW

Goal:

- Let either agent stop when it cannot proceed without human clarification,
  and optionally run several Igor/Rufus cycles without allowing an
  unbounded loop.

Dependencies:

- TASK-004 must be `COMPLETED`.

Scope:

- `orc.py`: handoff status parsing, persisted task states, resume validation,
  bounded round scheduling, deadline handling, and status rendering.
- `tests/test_orc.py` and fake-agent/PTY fixtures: both-role blocker states,
  clarification resumes, automatic cycles, limits, failures, and duplicate
  event handling.
- `README.md`, `design_docs/agent_workflow.md`, and `docs/roles.md`: document
  the state machine, handoff contract, resume rules, and bounded mode.
- Define the exact handoff status `UNABLE_TO_PROCEED` and require a concise
  reason from either Igor or Rufus.
- Persist blocker role, reason, task, round, thread, timestamp, current
  commit, and phase; pause without launching another role or retrying.
- Require a non-empty user clarification on the next `resume` and pass only
  that clarification as the user-provided request, without duplicating Orc's
  internal script prompt.
- Add an explicitly enabled automatic-cycle mode while preserving the current
  manual one-round pause behavior.
- Enable it only with the command form
  `begin DIRECTORY TASK-ID PROMPT --auto`; without `--auto`, Orc keeps the
  current one-round behavior.
- Accept `--max-rounds N` only with `--auto`, where `N` is an integer from 1
  through 5 and defaults to 5. Accept `--deadline-minutes N` only with
  `--auto`, where `N` is an integer from 1 through 1440 and defaults to 60.
  `resume DIRECTORY TASK-ID PROMPT` reuses the persisted settings and does not
  silently reset either limit.
- Persist round, cycle start, deadline, last role, last commit, and stop
  reason. Enforce at most five implementation/review rounds and a persisted
  wall-clock deadline, with a documented default of 60 minutes and an
  explicit pre-run way to choose another limit.
- Persist `automatic_rounds`, `max_rounds`, `deadline_seconds`,
  `cycle_started_at`, `deadline_at`, and `stop_reason` in the task record.
- Stop on completion, `UNABLE_TO_PROCEED`, child failure, deadline expiry, or
  the fifth round; never auto-resume after a clarification pause.

Acceptance criteria:

- Either agent can enter `UNABLE_TO_PROCEED`; Orc persists the blocker and
  starts no next role.
- Resume without clarification is rejected before child launch or state
  mutation; resume with clarification records exactly that request.
- Enabled automatic mode runs Igor then Rufus cycles and stops at the first
  completion signal.
- `begin DIRECTORY TASK-ID PROMPT --auto --max-rounds 5 --deadline-minutes 60` enables the bounded mode, while a begin without
  `--auto` remains manual; invalid combinations and out-of-range values are
  rejected before state mutation.
- No run launches more than five rounds or continues past its deadline,
  including while waiting for child idleness.
- Completion, clarification, deadline, fifth-round, child-failure, and
  normal manual-pause outcomes have distinct visible and persisted reasons.
- Duplicate idle events, stale notifications, and repeated resume requests
  cannot create extra rounds or concurrent roles.
- The manual one-round workflow remains available and documented.
- Tests cover both roles, malformed handoffs, persisted state, resume
  validation, clarification delivery, all stop conditions, and recovery.
- Applicable product, PTY/integration, documentation, and clean-diff checks
  pass.

## TASK-006 - Support Claude Code as an agent backend

State: NEW

Goal:

- Allow Orc to orchestrate Claude Code as an opt-in alternative backend while
  retaining Codex as the default.

Dependencies:

- TASK-005 must be `COMPLETED`.

Scope:

- `orc.py`: backend interface and selection, launch/resume commands,
  notification/idle reporting, prompts, environment, session identity,
  completion, and error interpretation.
- `tests/test_orc.py` and fake-backend/Linux PTY fixtures: both backends,
  begin, review, resume, handoffs, failures, unavailable commands, color,
  input, and clean exit.
- `README.md`: backend selection, Claude Code prerequisites, supported modes,
  limitations, configuration, and troubleshooting.
- Define a backend contract that preserves target directory semantics and the
  shared handoff fields: status, summary, files, verification, blockers,
  requested action, task, role, round, timestamps, thread, and target commit.
- Preserve current Codex command-line behavior and tests.
- Add `--backend codex|claude` to `begin`, defaulting to `codex`; `resume`
  reuses the backend persisted at begin and rejects a conflicting selection.
- For Claude, use the executable named by `ORC_CLAUDE_COMMAND`, defaulting to
  `claude`. Support Claude Code print mode only, using the capability contract
  `--print --output-format stream-json --input-format text`; reject a command
  whose `--help` does not expose those flags and `--resume`.
- Launch an initial Claude turn as
  `claude --print --output-format stream-json --input-format text PROMPT`.
  Resume the recorded session as
  `claude --print --output-format stream-json --input-format text --resume SESSION-ID PROMPT`.
- Store `backend`, `backend_command`, `backend_version`, and
  `claude_session_id` in task state. Capture the session ID and final response
  from the JSON stream; a clean exit without a valid handoff is an error.
- Provide the existing task, role, target-directory, and state-file context to
  Claude through the same environment and prompt contract used by Codex.
- Handle backend-specific output, color, input, timeout, failure, and idle
  behavior through the common PTY and task-state machinery.

Acceptance criteria:

- Claude Code can be selected for both roles without changing task or target
  directory semantics.
- `begin DIRECTORY TASK-ID PROMPT --backend claude` selects Claude, while an
  omitted selector uses Codex; the selector and command are visible in help,
  state, status, and README examples.
- Codex behavior remains unchanged and all Codex tests pass.
- The Claude capability probe, exact print/resume commands, session-ID
  persistence, stream parsing, and clean-exit handoff validation are covered
  by tests using a fake Claude executable.
- Claude begin, review, resume, handoff, failure, unavailable-command, and
  clean-exit paths are covered by tests.
- Missing or incompatible backend commands produce clear diagnostics.
- Backend-specific prompts and state cannot corrupt the shared task state.
- README examples match the implemented Linux command line and configuration.
- Applicable product, PTY/integration, documentation, and clean-diff checks
  pass.
