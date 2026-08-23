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

State: COMPLETED

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
  layout text. Extend the TASK-009 task segment deliberately to include the
  current automatic round in the exact form
  `<TASK-ID>: <status> · round N/M`, where `N` is the one-based current round
  and `M` is the configured maximum. Render the persisted round at terminal
  states, initialize the first visible round as `1`, and preserve the
  role-state, backend, agentbox, and right-anchored version information from
  TASK-009.
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
  bar after the hint and round-segment changes. Verify both Codex and Claude
  selection paths.

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
- The status bar renders the task segment exactly as
  `<TASK-ID>: <status> · round N/M`, with one-based `N` for the current
  automatic round and `M` equal to the configured maximum. The first visible
  round is `1`, and completed, paused, blocked, and stopped states retain the
  last persisted round value.
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

## TASK-012 - Improve retained UI, scrolling, and in-place resume

State: COMPLETED

Goal:

- Make Orc's retained terminal UI useful after a round by preserving the
  complete version rail, allowing each agent pane to be inspected through
  scrollback, and allowing a new automatic round to be started without
  exiting and restarting Orc.

Dependencies:

- TASK-011 must be `COMPLETED`.

Scope:

- `orc` status bar: fix the right-rail sizing and rendering so the complete
  `orc v0.0.1` text, including its leading separating space and final
  character, is displayed at the far right at every supported size in the
  Linux `xterm-256color` matrix of 120x40, 80x40, and 80x24. Terminals
  smaller than 80x24 are outside this task's support contract. Left-side
  clipping must stop before the reserved rail and must never clip, displace,
  or consume the version text.
- `orc` and the pane terminal model: retain sufficient per-pane scrollback to
  inspect output beyond the visible viewport, with independent scroll
  positions for Igor and Rufus. Retain at least 10,000 logical lines per
  pane; when that cap is reached, discard the oldest lines and make the new
  oldest retained line the Home position. The pane under the pointer is the
  scroll target; moving the pointer changes only the scroll target and never
  changes the active agent or forwards a click to an agent.
- `orc` pane input: Page Up and Page Down scroll the target pane by one
  viewport; Home scrolls to the oldest retained line; End scrolls to the
  newest output. These scrolling keys are consumed by Orc and are not sent
  to an agent. Up and Down remain agent input for prompt-history navigation
  and are sent only to the workflow-active agent. When any ordinary keyboard
  input, control input, Enter, or paste is sent to the active agent, its pane
  first scrolls to the bottom. New PTY output does not force a manually
  scrolled pane to the bottom until the user presses End or sends input to
  that agent.
- `orc` pane navigation: restore `Tab` as a scroll-target selector. Each
  press cycles the scroll target between Igor and Rufus, wrapping at either
  end. It changes only which pane receives scroll navigation; it does not
  change the workflow-active agent, highlighted agent border, or agent input
  destination. Keyboard input other than scroll navigation still goes only to
  the workflow-active agent's pane; it is never sent to the selected inactive
  scroll pane. `Tab` is not forwarded to an agent. This deliberately
  supersedes TASK-011's Tab pass-through rule for the scrolling UI.
- `orc` in-place resume: when the persisted task status is `paused`,
  `blocked`, or `completed` and both rendered role states are `inactive`, or
  when status is `stopped`, `stop_reason` is `child_failure`, exactly one
  role is `failed`, and the other is `inactive`, `Ctrl-R` opens an Orc-owned
  follow-up prompt instead of forwarding the key. The prompt accepts
  ordinary editing and paste, submits a non-empty request with Enter, and
  cancels with Escape. Submission retires any remaining child sessions,
  preserves the task ID, target directory, backend, backend command/version,
  task handoff history, and configured round/deadline limits, appends the
  request to `user_requests`, clears the current stop, blocker,
  child-failure, failed-role, and role-session metadata, sets `status: active`,
  `phase: implementer`, `round: 1`, and starts a fresh
  `cycle_started_at`/`deadline_at` window before launching Igor in the
  existing Orc process. An empty submission is rejected without changing
  task state. `Ctrl-R` has no resume effect while either role is active or
  when the status/role data is inconsistent.
- `README.md`, `design_docs/agent_workflow.md`, and CLI/UI help: document the
  complete version rail, independent pane scrollback and controls, the
  scroll-to-bottom-on-agent-input rule, the pointer-only scroll-target
  behavior, and the `Ctrl-R` in-place resume flow.
- `tests/test_orc.py` and Linux PTY/TUI fixtures: cover complete version text
  at Linux `xterm-256color` 120x40, 80x40, and 80x24, plus the out-of-scope
  smaller-size boundary; independent pane scroll positions; output older
  than the viewport and the 10,000-line cap; Page Up/Page Down/Home/End
  scrolling; Up/Down prompt-history forwarding; retained scroll position
  while PTY output arrives; scroll-to-bottom for keyboard, control, Enter,
  and paste input; pointer target changes without active-agent changes; and
  in-place resume for every eligible inactive-role status and the
  stopped-child-failure case, inconsistent-state no-op, cancellation,
  empty-input rejection, exact state preservation/reset, fresh deadline, and
  reset to round 1 without a process restart.

Acceptance criteria:

- The status bar always displays the complete `orc v0.0.1` segment at the
  far right, including the separating space and final character, without
  overlap or clipping at Linux `xterm-256color` 120x40, 80x40, or 80x24;
  smaller terminals are outside the support contract.
- Igor and Rufus each have retained, independently navigable scrollback.
  Page Up/Page Down, Home, and End have exactly the documented effects on
  the pane under the pointer and are not forwarded to an agent. Each pane
  retains at least 10,000 logical lines and Home reaches the oldest retained
  line after the cap discards older output. Up and Down remain available for
  prompt-history navigation in the workflow-active agent's PTY.
- `Tab` cycles the scroll target between Igor and Rufus without changing the
  workflow-active role, border, or agent input destination, and without being
  forwarded to an agent.
- Only the workflow-active agent's pane receives keyboard input. Selecting an
  inactive pane as the scroll target never makes it an input destination.
- New PTY output preserves a pane's manually selected scroll position, while
  any keyboard, control, Enter, or paste input sent to that pane first moves
  it to the bottom.
- Pointer movement can choose which pane receives scroll navigation but never
  changes the workflow-active role, border, or agent input destination.
- With status `paused`, `blocked`, or `completed` and both roles `inactive`,
  or status `stopped` with `stop_reason: child_failure`, one `failed` role,
  and one `inactive` role, `Ctrl-R` opens the follow-up prompt in the same
  Orc process. A non-empty Enter submission preserves the specified
  identity/configuration and handoff history, appends the request, clears
  stale terminal and failed-role metadata, starts a fresh deadline, and
  starts Igor with displayed round `1`. Escape, empty submission, active
  roles, and every other inconsistent status/role combination leave the
  terminal state unchanged.
- `Ctrl-R` does not interrupt or alter an active implementer or reviewer, and
  ordinary active-agent input continues to obey TASK-011's forwarding rules.
- Tests, CLI/UI help, README/workflow documentation, Linux PTY/TUI checks,
  and clean-diff verification pass on the final task commit.
