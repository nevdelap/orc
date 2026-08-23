# Implementation Plan

This file is the task source of truth for planned project work.

Before starting a new change, add one `NEW` task under `Tasks`. The shared state
transitions, commit contract, handoff procedures, review-document format, and
verification workflow are defined in `design_docs/agent_workflow.md`; role
responsibilities are defined in `docs/roles.md`.

## Tasks

## TASK-005 - Add bounded workflow control and clarification pauses

State: COMPLETED

Goal:

- Let either agent stop when it cannot proceed without human clarification,
  and optionally run several Igor/Rufus cycles without allowing an
  unbounded loop.

Dependencies:

- TASK-004 must be `COMPLETED`.

Scope:

- `orc`: handoff status parsing, persisted task states, resume validation,
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

## TASK-007 - Use agentbox identity and provide the `orc` launcher

State: COMPLETED

Goal:

- Make Orc recognize the confined agentbox environment and run Codex with
  `--dangerously-bypass-approvals-and-sandbox` there. This intentionally
  disables Codex confirmation prompts and its internal command sandbox because
  agentbox's confined Sysbox container is the external safety boundary
  described by `~/README.md`.
- Rename the executable source from `orc.py` to `orc`, so users can launch it
  as `./orc` while retaining the uv shebang and inline script metadata.

Dependencies:

- TASK-005 must be `COMPLETED`.

Scope:

- `orc`: detect the presence of `/etc/agentbox/identity` when constructing
  Codex begin and resume commands, and append
  `--dangerously-bypass-approvals-and-sandbox` when the marker exists. This is
  the exact Codex flag for skipping approval prompts and Codex sandboxing.
- Rename `orc.py` to the executable `orc`, preserve the existing uv shebang
  and PEP 723 metadata, and update all source, test, CI, workflow, and
  documentation references to the new path. Do not leave a second divergent
  `orc.py` implementation behind.
- Update test/module loading and static-tool configuration as needed so the
  extensionless `orc` source remains importable, linted, type-checked,
  compiled/validated, and covered by the existing test suite.
- `tests/test_orc.py` and Linux PTY/fake-Codex fixtures: verify command
  construction and execution with the marker present and absent for both
  implementer and reviewer launches, including resume.
- `README.md`: make `./orc` the canonical command, document the agentbox
  marker and resulting no-approval Codex mode, explain that agentbox provides
  the external safety boundary rather than Codex's or Claude's own prompts,
  and link to the [agentbox GitHub repository](https://github.com/nevdelap/agentbox)
  for that confinement model. The marker is an agentbox environment signal,
  not a user task option.
- Keep the detection based only on file existence. Do not trust or parse the
  marker contents, invoke a shell to obtain the mode, or add the flag when the
  marker is absent.
- Keep `CODEX_COMMAND` and `--codex` executable selection working, and append
  the flag as an argv element so paths containing spaces and non-shell
  executables remain supported.
- Preserve all existing prompt, notification, resume, PTY, handoff, and state
  behavior.

Acceptance criteria:

- With `/etc/agentbox/identity` present, every Codex begin and resume launch
  includes exactly `--dangerously-bypass-approvals-and-sandbox`.
- With the marker absent, Orc does not add
  `--dangerously-bypass-approvals-and-sandbox` to Codex launches; Codex's
  normal approval prompts and internal sandbox behavior remain unchanged.
- Both roles use the same rule, and begin and resume behave consistently.
- A clean checkout contains executable `orc` with a working uv shebang, and
  the documented `./orc` begin, resume, and help commands work without
  `uv run --script` or a file-extension-specific wrapper.
- No production, test, CI, workflow, or documentation path still requires
  `orc.py`; the renamed source is the single implementation.
- The implementation works with the default Codex executable and an explicit
  `CODEX_COMMAND`/`--codex` executable without invoking a shell wrapper.
- Tests prove that marker contents are irrelevant, including an empty marker
  and arbitrary non-empty contents.
- Tests prove that the flag is not duplicated when the configured executable
  or command already supplies it, or the implementation clearly rejects such
  a configuration with a documented diagnostic.
- README, `--help`/diagnostics, and CI accurately describe and validate the
  Linux-only behavior.
- Applicable product, PTY/integration, documentation, security, and clean-diff
  checks pass.

## TASK-006 - Support Claude Code as an agent backend

State: COMPLETED

Goal:

- Allow Orc to orchestrate Claude Code as an opt-in alternative backend while
  retaining Codex as the default.

Dependencies:

- TASK-007 must be `COMPLETED`.

Scope:

- `orc`: backend interface and selection, launch/resume commands,
  notification/idle reporting, prompts, environment, session identity,
  completion, and error interpretation.
- `tests/test_orc.py` and fake-backend/Linux PTY fixtures: both backends,
  begin, review, resume, handoffs, failures, unavailable commands, color,
  input, and clean exit.
- `README.md`: backend selection, Claude Code prerequisites, supported modes,
  limitations, configuration, troubleshooting, and the agentbox identity
  marker's external-sandbox rationale, with a link to the
  [agentbox GitHub repository](https://github.com/nevdelap/agentbox).
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
- If `/etc/agentbox/identity` exists, append
  `--dangerously-skip-permissions` to every Claude begin and resume command.
  This exact Claude flag disables Claude Code's own permission prompts. It is
  intentional because agentbox's confined Sysbox container is the external
  safety boundary described by `~/README.md`; do not infer the mode from the
  marker contents, and do not add the flag when the file is absent.
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
- The presence and absence of `/etc/agentbox/identity` are tested for both
  Claude begin and resume, including the exact
  `--dangerously-skip-permissions` flag when present and its absence outside
  agentbox; without the flag, Claude's normal permission behavior remains
  unchanged.
- Missing or incompatible backend commands produce clear diagnostics.
- Backend-specific prompts and state cannot corrupt the shared task state.
- README examples match the implemented Linux command line and configuration.
- Applicable product, PTY/integration, documentation, and clean-diff checks
  pass.

## TASK-008 - Make workflow status truthful and advance rounds reliably

State: COMPLETED

Goal:

- Make Orc's status bar accurately show the current state of both Igor and
  Rufus while using the available space efficiently.
- Make automatic implementation/review rounds advance after a normal handoff,
  even when the completed agent process remains alive waiting for input.

Dependencies:

- TASK-006 must be `COMPLETED`.

Scope:

- `orc`: derive separate implementer and reviewer display states from the
  persisted workflow phase, handoff events, child-session lifecycle, and
  current backend activity; refresh the status bar whenever any of those
  values changes.
- Make the begin prompt optional: support
  `begin DIRECTORY TASK-ID [PROMPT]`, persist an empty user prompt when it is
  omitted, and rely on Orc's built-in implementer prompt without appending an
  empty user-request section. Keep `resume DIRECTORY TASK-ID PROMPT` strict:
  a resume request or clarification must remain non-empty.
- Replace the current single active-role/layout status with a compact status
  bar that retains the task name, Orc version, pane-switch hint, both role
  states, the current task status, and an agentbox permission-mode indicator.
  Format the task segment as the task name plus its current status. Remove the
  layout label; the visible pane arrangement already communicates the layout.
- Define and display these role states consistently: `not started`, `active`,
  `waiting`, `inactive`, and `failed`. A role that has handed off and is
  waiting for the next workflow transition must not be shown as active merely
  because its Codex or Claude child process still exists. Once the task is
  complete, both roles display `inactive`.
- When `/etc/agentbox/identity` exists and the selected backend launch
  command contains the exact no-permission flag for that backend, show an
  explicit `agentbox: no-permissions` indicator. Use
  `--dangerously-bypass-approvals-and-sandbox` for Codex and
  `--dangerously-skip-permissions` for Claude; do not show the indicator when
  the marker is absent or the launch mode is not actually enabled.
- On a normal handoff, retire or reset the completed child session before
  scheduling the next role. Its ordinary completion must not be recorded as a
  `child_failure`, and a live completed child must not block the next
  automatic round or cause duplicate concurrent launches.
- When the task reaches its normal completion state, keep Orc's UI alive after
  the final reviewer handoff. Do not call `exit` merely because the task is
  complete; leave both panes and the final status visible until the user
  explicitly quits with `Ctrl-Q`. Completion must not launch another role.
- Preserve the existing manual-pause, clarification, deadline, max-round,
  completion, backend, PTY, and resume semantics.
- `tests/test_orc.py` and Linux PTY/integration fixtures: cover both roles,
  both Codex and Claude backend modes where applicable, normal and failed
  child exits, automatic round transitions, status refresh, pane focus, and
  terminal resize.
- `README.md` and `design_docs/agent_workflow.md`: document the compact status
  bar, role-state meanings, agentbox indicator, and completed-child lifecycle.
- Update CLI help, README examples, workflow documentation, and tests to show
  both begin forms and the unchanged non-empty resume requirement.

Acceptance criteria:

- The status bar simultaneously shows current implementer and reviewer states
  and refreshes after launch, handoff, child exit, idle-hook processing, and
  workflow stop/completion events.
- A completed Igor handoff displays Igor as `waiting` while the task remains
  active, and does not display Rufus as `active` until Rufus has actually been
  launched.
- A completed Rufus handoff displays Rufus as `waiting` while Orc is waiting
  to launch the next Igor round, and does not display Rufus as `active`.
- The layout label is absent while task name, Orc version, pane-switch hint,
  both role states, and the relevant agentbox indicator remain visible at the
  supported terminal sizes; the task name also includes current task status.
- `begin DIRECTORY TASK-ID` is accepted and uses only the built-in implementer
  prompt until a user request is supplied; `begin DIRECTORY TASK-ID PROMPT`
  continues to record and deliver the supplied prompt exactly.
- An omitted begin prompt does not create an empty user request, and
  `resume DIRECTORY TASK-ID PROMPT` still rejects an empty or whitespace-only
  request before changing state.
- After normal task completion, the status bar reports the completed task
  status and both roles as `inactive`; Orc remains alive with the final panes
  visible and exits only after the user presses `Ctrl-Q`.
- With `/etc/agentbox/identity` present, Codex shows
  `agentbox: no-permissions` only when
  `--dangerously-bypass-approvals-and-sandbox` is in its launch argv, and
  Claude shows it only when `--dangerously-skip-permissions` is in its launch
  argv. Outside agentbox, neither indicator is shown.
- In automatic mode, a normal Igor handoff followed by Rufus review starts
  the next Igor round without manual input, even if the prior child process
  has not exited on its own.
- Normal completed child sessions are retired without `child_failure`; real
  non-zero or unexpected child exits still produce the existing failure stop.
- Duplicate handoffs, stale events, repeated polling, and terminal resize do
  not produce duplicate launches or incorrect role states.
- Manual one-round mode, clarification pauses, deadline/max-round limits,
  Codex behavior, Claude behavior, and resume behavior remain unchanged.
- Tests, Linux PTY/integration checks, documentation checks, and clean-diff
  verification pass on the final commit.
