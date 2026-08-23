# Implementation Plan

This file is the task source of truth for planned project work.

Before starting a new change, add one `NEW` task under `Tasks`. The shared state
transitions, commit contract, handoff procedures, review-document format, and
verification workflow are defined in `design_docs/agent_workflow.md`; role
responsibilities are defined in `docs/roles.md`.

## Tasks

## TASK-009 - Improve status-bar clarity and visual hierarchy

State: COMPLETED

Goal:

- Make Orc's compact status bar easier to scan by using consistent task-status
  formatting, semantic colors, and a stable left/right layout.
- Preserve all existing workflow information and terminal behavior while
  making warnings and failures legible against the current dark-grey bar.

Dependencies:

- TASK-008 must be `COMPLETED`.

Scope:

- `orc`: revise status-bar composition so the task segment is exactly
  `<TASK-ID>: <status>` for every persisted task status, remove the redundant
  `Click a pane to focus` hint, retain the useful pane-switch and quit hint,
  and reserve a right rail containing the complete `orc v0.0.1` version
  segment, including the separating space, regardless of the width consumed by
  the left-side information. Left-side content may be clipped at that rail.
- `orc`: apply semantic styling to task states, role states, backend text, and
  the agentbox indicator without changing their persisted values or workflow
  semantics. The complete persisted task-status set is `active`, `paused`,
  `blocked`, `stopped`, and `completed`: use green for `active` and
  `completed`, amber for `paused`, `blocked`, and `stopped`, grey for role
  states `inactive`, `not started`, and `waiting`, light red for role state
  `failed`, light red for
  `agentbox: no-permissions`, and white for both `backend: codex` and
  `backend: claude`. Stop reasons do not change the `stopped` task color;
  failure is conveyed by the affected role's `failed` state. Keep the colors
  readable on Orc's dark-grey status-bar background and do not rely on color
  alone to convey a state.
- Product direction recorded and operator-accepted: Nev explicitly directed
  that `waiting` use the readable grey role style and both backend labels use
  white.
- `tests/test_orc.py` and Linux PTY/TUI fixtures: cover every rendered task
  status and role state, the no-permissions indicator, the exact colon task
  format, removal of the click-to-focus text, retention of useful key hints,
  right anchoring and non-overlap of the version segment and the documented
  segment order at
  the exact supported terminal matrix of Linux `xterm-256color` at 120x40
  (side-by-side), 80x40 (stacked), and 80x24 (single-pane), including the
  constrained-width priority rules and readable semantic styling for the
  dark-grey background.
- `README.md` and `design_docs/agent_workflow.md`: document the colon task
  format, the exact status-bar segment order and constrained-width priority
  rules, the right-anchored Orc version, the retained keyboard hints, and the
  semantic color meanings including backend text and the light-red
  no-permissions warning.

Acceptance criteria:

- For every task status Orc renders the task segment as exactly
  `<TASK-ID>: <status>`; no task status uses the previous middot form.
- The status bar no longer says `Click a pane to focus`. It still explains
  the supported pane-switch and quit keys, and all those keys retain their
  existing behavior and forwarding rules.
- The supported UI matrix is Linux `xterm-256color` at 120 columns by 40 rows
  (side-by-side), 80 by 40 (stacked), and 80 by 24 (single-pane); terminals
  smaller than 80 by 24 are outside this task's support contract.
- The left-to-right status order is task, Igor, Rufus, backend, optional
  `agentbox: no-permissions`, and the retained `Tab switches panes · Ctrl-Q exits` hint. A fixed right rail contains the single `orc v0.0.1` segment.
  Shown segments are separated by spaces and a center dot (`·`); the task
  segment's logical text remains exactly `<TASK-ID>: <status>`. The right rail
  always reserves enough width for a separating space and the complete
  `orc v0.0.1` segment. At 120x40, 80x40, and 80x24, left-side segments keep
  their complete logical text and any overflow is clipped at the left-rail
  boundary; it may not overlap, displace, or clip the right-anchored version
  segment, and no content wraps.
- `active` and `completed` are visibly green; `paused`, `blocked`, and
  `stopped` are visibly amber; `inactive` and `not started` are visibly grey;
  `waiting` uses the readable grey role style; `failed` and
  `agentbox: no-permissions` are visibly light red; and both backend labels
  use the documented white style against the dark-grey background.
- Status labels remain explicit and readable when colors are unavailable or
  indistinguishable; styling is an enhancement rather than the only state
  signal. The no-permissions warning remains distinguishable from a failure
  through its label and styling.
- The status bar continues to compose both role states, the current task
  status, selected backend, agentbox indicator when enabled, and the retained
  key hints without changing any persisted task state or workflow transition;
  rendered left-side content may be clipped when it exceeds the space left
  after reserving the version rail; the complete version segment and its
  separating space are never clipped.
- Tests exercise all five persisted task statuses, all five role states,
  normal and stopped workflows, both backend labels, agentbox enabled and
  disabled modes, the 120x40, 80x40, and 80x24 terminal matrix, and the
  rendered order, clipping boundary, right-rail alignment, and styling
  contract through the real TUI or an equivalent fixture that verifies the
  actual composed widgets.
- README, workflow documentation, Linux PTY/TUI checks, and clean-diff
  verification pass on the final task commit.

## TASK-010 - Restore terminal-state UI lifetime

State: COMPLETED

Goal:

- Restore the workflow behavior that was required but not fully implemented:
  keep the Orc TUI available after orchestration reaches any terminal or
  waiting state, so the user can inspect the final panes, status, handoffs,
  and failure details before explicitly quitting with `Ctrl-Q`.

Background and failure being corrected:

- TASK-008's accepted workflow contract required Orc to keep the completed
  panes and status visible until the user quits with `Ctrl-Q`; TASK-009 did
  not change that lifecycle contract. The current implementation still calls
  `self.exit()` from the deadline, paused/blocked/stopped, and child-failure
  paths, so the previously accepted behavior is missing in those paths. This
  task is a corrective implementation of that unmet requirement, not a
  rework of TASK-009's status-bar presentation.

Dependencies:

- TASK-008 must be `COMPLETED`.
- TASK-009 must be `COMPLETED`.

Scope:

- `orc`: change the application lifecycle so that reaching `completed`,
  `paused`, `blocked`, or `stopped` does not call `self.exit()` or otherwise
  terminate the TUI. This includes normal completion, clarification pauses,
  manual pauses, deadline expiry, maximum-round termination, and child
  failures.
- `orc`: when a deadline or child failure is detected, persist the terminal
  state and its existing diagnostic metadata exactly as today, refresh the
  status bar and panes, retire/close any completed child sessions safely, and
  stop scheduling or launching further roles while the UI remains running.
- `orc`: retain `Ctrl-Q` as the explicit user-controlled exit path. Quitting
  must perform the existing PTY, reader, timer, and child cleanup without
  deleting or rewriting the task record merely because the UI was closed.
- `tests/test_orc.py` and any Linux PTY/TUI fixtures: cover every terminal
  status and stop reason, including transitions caused by polling, deadline
  expiry, clean completion, unexpected implementer/reviewer exit, and
  clarification. Verify that the app remains mounted and that no new role is
  launched after termination.
- `README.md` and `design_docs/agent_workflow.md`: describe that Orc remains
  alive for inspection in all terminal states and exits only when the user
  presses `Ctrl-Q`; document that task state remains available after quitting.

Acceptance criteria:

- The implementation and review explicitly compare the changed lifecycle
  paths with TASK-008's accepted keep-alive requirement and demonstrate that
  the correction is limited to terminal-state lifetime and cleanup; no
  TASK-009 status-bar behavior is reimplemented or changed.
- A task with status `completed` keeps both final panes and the final status
  bar visible until the user presses `Ctrl-Q`.
- Tasks with status `paused`, `blocked`, or `stopped` likewise keep the UI
  visible, including `clarification`, `manual_pause`, `deadline`,
  `max_rounds`, and `child_failure` stop reasons.
- Deadline and child-failure handling still records the same stop reason and
  diagnostic fields, but neither path exits the app or launches another
  implementer/reviewer.
- Polling a terminal record repeatedly is idempotent: it does not respawn
  sessions, duplicate handoffs, mutate terminal metadata, or repeatedly
  request application exit.
- `Ctrl-Q` remains the explicit exit action, and its cleanup leaves the
  persisted task record intact and does not leave child processes or PTY
  readers behind.
- Tests exercise all terminal statuses, all terminal stop reasons, clean and
  failed child exits, repeated polling, and the explicit quit path through
  the real app lifecycle or an equivalent fixture.
- README, workflow documentation, applicable Linux PTY/TUI checks, and
  clean-diff verification pass on the final task commit.

## TASK-011 - Simplify automatic workflow, CLI, and pane interaction

State: NEW

Goal:

- Make automatic multi-round orchestration the only workflow mode, simplify
  the command interface, make backend selection explicit and configurable,
  and ensure the UI's active-agent border reflects the workflow rather than a
  separately selectable pane.

Dependencies:

- TASK-010 must be `COMPLETED`.

Scope:

- `orc` CLI: remove the `--auto` option and its manual one-round behavior.
  Every `begin` starts the bounded automatic Igor/Rufus cycle. Retain
  `--max-rounds` with the existing range of 1 through 5 and default of 5,
  and retain `--deadline-minutes` with the existing range of 1 through 1440
  and default of 60. Both limits remain persisted and reused on resume.
- `orc` CLI: make the canonical commands exactly
  `./orc begin DIRECTORY TASK-ID [PROMPT] [--max-rounds N] [--deadline-minutes N] [--codex|--claude]` and
  `./orc resume TASK-ID PROMPT`. The begin prompt remains optional; the
  resume request remains required and non-empty.
- `orc` CLI: replace the current backend interface with mutually exclusive
  `--codex` and `--claude` selector flags on `begin`. If neither flag is
  supplied, read `ORC_BACKEND`, accepting only `codex` or `claude`. If no
  selector and no valid environment default are supplied, fail with an
  actionable error before creating state or launching a child; there is no
  built-in backend fallback. Keep `CODEX_COMMAND` and
  `ORC_CLAUDE_COMMAND` as executable-path configuration, distinct from the
  backend selector. Persist the selected backend and reuse it on `resume`;
  `resume` must not accept a different backend selector.
- `orc` CLI and state handling: remove the resume directory argument and
  resolve the target directory only from the normalized directory persisted
  by `begin`. Reject missing or invalid stored target data before changing
  state or launching a child. Remove redundant backend, manual-mode, and
  directory-mismatch help and error paths while retaining useful state-file,
  limit, and troubleshooting diagnostics.
- `orc` UI: remove local pane switching through mouse clicks, `Tab`,
  `Shift-Tab`, `1`, or `2`. Those inputs must no longer change an active pane
  or workflow role. `Tab` is forwarded as byte `0x09`, `Shift-Tab` as the
  terminal sequence `ESC [ Z`, and `1` and `2` as their single ASCII bytes to
  the currently active agent PTY. A mouse press or release over either pane
  is consumed as a no-op: it is never encoded or forwarded to an agent, and
  it never changes the active role. The highlighted border remains, but is
  named and documented as the active-agent indicator.
- `orc` UI: define the active-agent mapping explicitly. While the persisted
  task status is `active` and `phase` is `implementer`, Igor is the sole
  active role; while status is `active` and `phase` is `reviewer`, Rufus is
  the sole active role. For `paused`, `blocked`, `stopped`, and `completed`,
  neither role is active. The border follows this mapping, and input other
  than `Ctrl-Q` is ignored when neither role is active.
- `orc` state handling: migrate an existing record with a valid persisted
  target directory and backend when resuming it. If `automatic_rounds` is
  missing or false, preserve its task, round, handoffs, requests, target, and
  backend data, set automatic mode true, use existing valid limits or the
  defaults of 5 rounds and 60 minutes, and start a fresh persisted deadline
  from the resume time. Existing valid automatic records reuse their stored
  limits and deadline. A record missing a valid `codex`/`claude` backend or a
  valid target directory is rejected with an actionable error before any
  mutation; resume never guesses a backend.
- `orc` UI and status bar: remove the pane-switching hint and all
  focus-selection terminology, keep the quit hint, and remove any redundant
  layout text. Preserve the task/status, role-state, backend, agentbox, and
  right-anchored version information established by TASK-009.
- `README.md`, `design_docs/agent_workflow.md`, and CLI help: document the
  automatic-only lifecycle, exact begin/resume syntax, selector precedence,
  `ORC_BACKEND` values and required-error behavior, persisted-directory
  resume, active-agent border semantics, and pass-through behavior for the
  formerly intercepted keys. Remove stale manual-round, `--auto`, resume
  directory, click-to-focus, and pane-switching instructions.
- `tests/test_orc.py` and Linux PTY/TUI fixtures: cover command parsing and
  help, selector precedence and invalid/missing backend configuration,
  persisted backend and target-directory resume, automatic defaults and
  limits, rejection of removed syntax, pass-through of click/Tab/
  Shift-Tab/1/2, active-agent border transitions, and the constrained status
  bar after the hint changes. Verify both Codex and Claude selection paths.

Acceptance criteria:

- `begin` always starts bounded automatic orchestration; `--auto` is absent
  from parsing and help, and no manual one-round mode remains.
- The default automatic bounds remain five rounds and 60 minutes, with the
  documented validation ranges and persisted resume behavior.
- `begin` accepts exactly one of `--codex` or `--claude`, otherwise uses a
  valid `ORC_BACKEND` value, and otherwise fails before state mutation. No
  implicit Codex or Claude fallback exists. Backend executable variables are
  still honored independently.
- `resume TASK-ID PROMPT` loads the original target directory and backend
  from state, rejects the old directory-taking form, and performs all
  validation before state mutation or child launch.
- Mouse clicks cannot switch panes, alter the active role, or reach an agent.
  When `active/implementer` or `active/reviewer` is persisted, `Tab`,
  `Shift-Tab`, `1`, and `2` reach only that role's PTY using the exact byte or
  sequence contract in Scope. In all other statuses they are ignored. The
  border and status identify the mapped workflow-active role; no local focus
  hint or layout section remains in the bar.
- A legacy record with `automatic_rounds` missing or false is upgraded only
  after all resume validation succeeds, retains its existing task history,
  and receives the documented automatic defaults and new deadline. A record
  with missing/invalid target or backend is rejected without state mutation.
- Existing automatic handoff, clarification, agentbox no-permissions, and
  Ctrl-Q behavior continue to work for both backends, with no regression to
  TASK-010's requirement that terminal-state UIs remain alive.
- Tests, CLI help, README/workflow documentation, Linux PTY/TUI checks, and
  clean-diff verification pass on the final task commit.
