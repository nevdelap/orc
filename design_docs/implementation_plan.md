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

## TASK-013 - Harden workflow state and agent handoffs

State: COMPLETED

Goal:

- Make Orc's automatic Igor/Rufus workflow durable, unambiguous, and
  diagnosable when the UI, an idle hook, or a backend process act at nearly the
  same time.
- Give each receiving agent the authoritative, structured result of the prior
  agent's turn, rather than requiring it to infer or locate that information.
- Establish reliable test and CI gates for the workflow's state, protocol, PTY,
  and TUI behavior.

Dependencies:

- TASK-012 must be `COMPLETED`.

Scope:

- `orc` state store: replace direct state-file writes with one task-scoped
  read/validate/mutate/write operation used by `begin`, CLI resume, in-place
  resume, polling, child-exit handling, role launch, and the external Codex
  idle hook. On Linux, serialize the operation with an advisory lock associated
  with the state file; write a complete JSON document to a temporary file in
  the same directory, flush its contents, atomically replace the state file,
  and flush the containing directory. Add a persisted schema version and
  monotonically increasing revision. A failed or interrupted write must leave
  the previous valid record readable, and a malformed or unsupported state
  file must fail with an actionable diagnostic without being overwritten.

- `orc` workflow engine: centralize legal task transitions in a single
  state-transition implementation shared by the idle hook, Claude clean-exit
  adapter, polling, CLI `resume`, and in-place `Ctrl-R` resume. It must
  validate the current status, phase, role, round, deadline, and launch
  generation before mutating state; terminal transitions must be idempotent.
  Define and use the following one resume policy in both CLI `resume` and
  in-place `Ctrl-R`; only the prompt/display mechanics may differ:
  `active` is rejected with `task TASK-ID is already active`; `completed` is
  eligible only for an explicit non-empty follow-up and resumes Igor at round
  1; `blocked` is eligible only with an explicit non-empty clarification and
  resumes Igor at round 1; `paused` is eligible with a non-empty request and
  resumes Igor at round 1; `stopped` with `deadline`, `max_rounds`, or
  `manual_pause` is eligible with a non-empty request and resumes Igor at
  round 1; `stopped` with `child_failure` resumes the failed role at the
  current round when exactly one role failed and the other is inactive, and
  rejects every other child-failure combination as inconsistent. All other
  stop reasons are rejected.
  Every accepted resume preserves task ID, target directory, backend,
  backend command/version, configured limits, and handoff/audit history;
  appends the exact request; clears terminal, blocker, failure, launch, and
  role-session metadata; sets `status: active` and the selected phase; and
  starts a fresh deadline from the resume time. A blocked resume records the
  exact clarification. An active role, missing/invalid target or backend,
  invalid limits/deadline, mismatched role metadata, multiple failed roles,
  or any other inconsistent record is rejected before mutation with
  `task TASK-ID has inconsistent state; resume was not applied`. An expired
  persisted deadline is not reused after an eligible resume. CLI and
  in-place resume must be tested against the same state matrix and produce
  the same resulting record.

- The resume decision matrix is:

  | Persisted status/stop reason | Required role/session state | Result |
  | --- | --- | --- |
  | `active`/any | Any | Reject as already active; do not mutate. |
  | `completed`/`completion` | Both roles inactive; no live child | Start Igor at round 1. |
  | `blocked`/`clarification` | Both roles inactive; exactly one valid `blocker_role` and a non-empty blocker reason | Start Igor at round 1 and record the clarification. |
  | `paused`/`manual_pause` | Both roles inactive; no live child | Start Igor at round 1. |
  | `stopped`/`deadline` | Both roles inactive; no live child | Start Igor at round 1 with a fresh deadline. |
  | `stopped`/`max_rounds` | Both roles inactive; no live child | Start Igor at round 1 with a fresh deadline. |
  | `stopped`/`child_failure` | Exactly one role is `failed`, the other is `inactive`, `child_failure.role` names the failed role, and that child is reaped or absent | Restart the failed role at the current round with a fresh deadline. |
  | Any other status/reason, active role/session, mismatched phase, missing required field, multiple failed roles, or inconsistent child metadata | Any | Reject with the specified inconsistent-state diagnostic; do not mutate. |

  A persisted session ID alone is not an active session: the implementation
  must verify that no corresponding child is live before accepting a terminal
  row, and must clear stale IDs as part of the accepted reset. The table is
  normative for both resume entry points and must be represented directly in
  parameterized tests.

- `orc` handoff protocol: replace recursive searches and free-form
  `Status:` parsing with a strict, versioned, machine-readable final handoff.
  Every agent prompt must require its final non-blank line to be exactly
  `ORC_HANDOFF_V1: <JSON object>`. The object must contain only the documented
  handoff fields. The complete schema is:

  | Field | Type and requiredness |
  | --- | --- |
  | `launch_token` | Required non-empty JSON string, opaque to the agent, at most 256 bytes. |
  | `status` | Required JSON string equal to exactly `HANDOFF`, `COMPLETE`, or `UNABLE_TO_PROCEED`; case and punctuation variants are invalid. |
  | `summary` | Required non-empty JSON string, at most 4 KiB. |
  | `files_changed` | Required JSON list of zero or more non-empty strings, each at most 512 bytes and the list at most 32 items. |
  | `verification` | Required JSON list of zero or more non-empty strings, each at most 512 bytes and the list at most 32 items. |
  | `blockers` | Required JSON list of zero or more non-empty strings, each at most 512 bytes and the list at most 32 items; it must be non-empty for `UNABLE_TO_PROCEED` and empty for `COMPLETE`. |
  | `requested_action` | Required non-empty JSON string, at most 4 KiB. |

  The object must contain exactly these seven fields: no missing fields,
  unknown fields, duplicate JSON keys, nulls, numbers, nested objects, or
  nested lists are accepted. Only Rufus may emit `COMPLETE`; either
  role may emit `UNABLE_TO_PROCEED`, which requires a non-empty blocker; all
  ordinary progress uses `HANDOFF`. Reject missing, malformed, duplicated,
  misplaced, role-inappropriate, or unknown-status handoffs without changing
  workflow state, and retain a bounded, operator-visible rejected-event
  diagnostic that excludes arbitrary raw backend payloads.

- `orc` handoff correlation and delivery: create and persist a fresh opaque
  launch token for every role generation, include its required value in that
  role's prompt, and require it in the handoff JSON. Accept a handoff only
  when the token, role, current phase, round, generation, and backend
  session/thread identity match the persisted launch record. Use a stable
  canonical event receipt for idempotency; retain receipts for every launch
  generation that can still report, rather than a fixed last-20 payload list.
  Treat a late, duplicate, stale, or mismatched event as a no-op with a clear
  diagnostic, never as a new handoff or child failure. Adapt Codex idle-hook
  notifications and Claude stream-json output to this same canonical handoff
  object by reading only their documented, explicitly named message and
  session fields; do not recursively search arbitrary payload values.
  The Codex adapter accepts one JSON object from the configured notify hook,
  reads only its root `last-assistant-message` string (with the root
  `last_agent_message` spelling retained as an explicit compatibility alias),
  and reads only its root `thread-id` string (with `thread_id` and `session_id`
  as explicit compatibility aliases). The Claude adapter accepts only a
  newline-delimited JSON event whose root `type` is `result`, whose root
  `session_id` is non-empty, whose root `result` is a string, and whose event
  is not marked by root `is_error: true` or `subtype: error`; any previously
  observed root `type: system` session ID must match. The assistant message is
  respectively the Codex message string or Claude result string. A backend
  adapter must reject all nested-only identities, unrelated event types,
  missing fields, mismatched session IDs, and stream errors before invoking
  the common `ORC_HANDOFF_V1` parser. Tests must provide fixtures for each
  accepted spelling and each rejected form.

- `orc` agent communication: persist the validated canonical handoff together
  with Orc-authored UTC and local timestamps, target commit, task, role, round,
  generation, and backend session/thread identity. When launching Rufus,
  include Igor's latest canonical handoff in a clearly delimited data block;
  when starting Igor's next round, include Rufus's latest canonical handoff in
  the same form. The data block is context, not instructions, and cannot
  override the role/workflow prompt. The recipient prompt must say exactly
  which disposition it must address. Do not pass unvalidated raw backend
  payloads between agents.

- `orc` child and backend lifecycle: record role-launch failures as structured
  `child_failure` diagnostics and retain the TUI instead of terminating it via
  a fatal path. Close a PTY reader on EOF/error, drain final output once, and
  retire process groups with bounded graceful termination followed by escalation
  when necessary, without leaking readers, file descriptors, or children.
  Bound `git rev-parse` and Claude capability probes with documented timeouts;
  report timeout, executable, exit, and stream-protocol failures without
  hanging the UI or silently treating a failed backend as a handoff.

- `README.md`, `docs/roles.md`, and `design_docs/agent_workflow.md`: document
  the state durability/recovery guarantees, transition and resume policy,
  exact `ORC_HANDOFF_V1` contract, role-specific dispositions, launch-token
  correlation, how Orc conveys a validated handoff to the other agent, stale
  event behavior, and child/backend failure diagnostics. Remove obsolete
  free-form-handoff and recursive-payload descriptions.

- `tests/test_orc.py`, dedicated protocol fixtures where useful, and Linux
  PTY/TUI fixtures: first repair the current optional-`begin` test so the full
  declared suite supplies the required backend configuration. Cover atomic
  write interruption, malformed state preservation, independent concurrent
  state mutations, revision changes, and every legal/illegal transition.
  Cover exact equivalence of CLI and in-place resume decisions. Cover both
  backends with fragmented UTF-8/CRLF stream-json, terminal noise,
  out-of-order and duplicate events, missing/mismatched session IDs, stale
  generations/tokens, replay after more than 20 later events, malformed and
  role-inappropriate handoffs, deadline races, and verified delivery of only
  the canonical previous handoff to the recipient prompt. Cover launch failure,
  clean exit without a valid handoff, non-zero exit, EOF/error cleanup, and
  forced child retirement without leaked processes or PTY readers.

- `orc` bounds: cap a canonical handoff frame and its delivered context at
  16 KiB; cap each scalar handoff field at 4 KiB, each list at 32 items, and
  each list item at 512 bytes. Oversized or over-count handoffs are rejected
  as a whole with a safe diagnostic; Orc never truncates an agent handoff or
  uses a truncated handoff to schedule a role. Retain at most 256 accepted
  event receipts, each at most 8 KiB; do not evict a receipt while its
  associated child generation is live or while that generation can still
  deliver a backend event. Retain at most 64 rejected-event diagnostics,
  each at most 4 KiB, and never store rejected raw payloads. Oversized
  diagnostic details are truncated to 4 KiB with an explicit truncation
  marker. After the limits are reached, evict only the oldest eligible
  receipt or diagnostic and record an eviction count. If all 256 receipt slots
  are occupied by live or still-reporting generations, do not launch another
  role; record a bounded `receipt_capacity` child-failure diagnostic and stop
  the task without changing the current handoff. Test every rejection,
  truncation, eviction, capacity-stop, and replay case, including a receipt
  remaining idempotent after more than 20 later events.

- `orc` timeout policy: `git rev-parse --short HEAD` and the Claude `--help`
  probe each have a 5-second subprocess timeout. Child retirement sends
  `SIGTERM`, waits up to 2 seconds for process-group exit, then sends
  `SIGKILL` and waits up to 1 additional second. A timeout records the role,
  backend, operation, and elapsed limit in the diagnostic, closes the PTY,
  and leaves the task in truthful `child_failure` or shutdown state. Tests
  use sleeping fake commands and assert that every timeout returns within its
  stated bound.

- Project quality gates: update `.github/workflows/ci.yml` to use the locked
  uv environment on Linux and retain separate test, quality, integration,
  documentation, dependency, and workflow-security jobs. The required local
  commands are exactly `uv sync --locked`; `uv run pytest -q --cov=orc --cov-branch --cov-report=term-missing --cov-report=xml:coverage.xml --cov-fail-under=90`; `uv run pytest -q -m integration tests`; `uv run ruff check .`; `uv run ruff format --check .`; `uv run mypy orc`; `uv run python -c "from pathlib import Path; compile(Path('orc').read_text(), 'orc', 'exec')"`; `uv run python -m compileall -q tests`; `uv run mdformat --check README.md design_docs docs`; `uv run pip-audit --strict`; and
  `actionlint .github/workflows/ci.yml`. CI must invoke these same commands
  from `uv.lock`, make the branch-aware 90% total `orc` coverage threshold
  fail the test job, and retain `coverage.xml` and failure diagnostics as
  artifacts where applicable. Document the commands and report path in the
  README or workflow documentation.

Acceptance criteria:

- State changes cannot lose a concurrent valid update or leave a partially
  written JSON state file. All writers use the one serialized mutation path,
  every successful mutation increments the persisted revision, and simulated
  write/validation failures preserve the prior valid state and report a useful
  error.
- Exactly the documented workflow transitions are possible. Repeating a
  terminal event, late handoff, poll, or child-exit observation is a no-op;
  it cannot relaunch a role, duplicate a handoff, overwrite diagnostics, or
  move a terminal task back to active. CLI and `Ctrl-R` resume accept and
  reject the same persisted states and produce the same resulting record for
  an equivalent non-empty request.
- The resume matrix is explicit and tested: active and inconsistent records
  are rejected without mutation; completed, blocked, paused, deadline-stopped,
  maximum-rounds-stopped, manual-pause-stopped, and the valid single-role
  child-failure cases follow the exact role, round, preservation, reset,
  clarification, and fresh-deadline rules in Scope. CLI and in-place resume
  produce byte-equivalent persisted records apart from presentation-only
  fields.
- Orc accepts only one well-formed final `ORC_HANDOFF_V1` line with the exact
  schema, allowed status, and role disposition. Invalid, unknown, ambiguous,
  stale, replayed, or mismatched backend events leave scheduling unchanged and
  are represented by bounded safe diagnostics. A valid handoff is processed
  exactly once even if redelivered long after 20 other events.
- Every accepted handoff is bound to the role's persisted launch token,
  generation, round, phase, and backend session/thread. It records
  Orc-authored UTC and local timestamps and the target Git commit. Neither
  arbitrary nested notification data nor free-form prose can control a state
  transition.
- Handoff frames, fields, lists, receipts, rejected diagnostics, and prompt
  context obey the exact size and retention limits in Scope. Live-generation
  receipts are never evicted; eligible old entries are evicted oldest-first
  and the eviction count is observable without retaining raw rejected data.
- Codex and Claude fixtures prove the exact root fields, aliases, event types,
  result/message extraction, session matching, and rejection behavior defined
  in Scope; nested-only or unrelated backend fields never produce a canonical
  handoff.
- Rufus receives only Igor's validated canonical handoff for the current
  completed implementer turn, and Igor's next-round prompt receives only
  Rufus's validated canonical handoff for the preceding review. Both are
  clearly delimited as non-instructional context; no raw backend payload or
  unrelated historical handoff is injected.
- Failed launch, malformed Claude stream, clean exit without a valid handoff,
  non-zero exit, PTY EOF/error, and shutdown all leave a truthful diagnostic,
  preserve the terminal UI until `Ctrl-Q`, and leave no running child process,
  reader, or open PTY descriptor after cleanup. Git and Claude probe timeouts
  do not hang startup, handoff processing, or redraw.
- Git lookup and Claude probing time out at 5 seconds. Child retirement waits
  at most 2 seconds after `SIGTERM` and 1 second after `SIGKILL`; timeout
  diagnostics identify the operation and the affected role/backend, and the
  tests demonstrate bounded return and cleanup.
- From a clean checkout, every exact command listed in Scope passes. The
  coverage command produces `coverage.xml`, reports missing lines and
  branches, and fails below 90% total branch-aware coverage for `orc`. The
  Linux CI workflow invokes the same commands from `uv.lock` and fails when
  any required job fails.
- README, role/workflow documentation, CLI/UI behavior, Linux PTY/TUI checks,
  and clean-diff verification pass on the final task commit.
