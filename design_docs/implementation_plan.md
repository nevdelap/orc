# Implementation Plan

This file is the task source of truth for planned project work.

Before starting a new change, add one `NEW` task under `Tasks`. The shared state
transitions, commit contract, handoff procedures, review-document format, and
verification workflow are defined in `design_docs/agent_workflow.md`; role
responsibilities are defined in `docs/roles.md`.

## Tasks

## TASK-009 - Improve status-bar clarity and visual hierarchy

State: NEW

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
  and anchor the complete `orc v0.0.1` version segment at the far right of the
  bar regardless of the width consumed by the left-side information.
- `orc`: apply semantic styling to task states, role states, backend text, and
  the agentbox indicator without changing their persisted values or workflow
  semantics. The complete persisted task-status set is `active`, `paused`,
  `blocked`, `stopped`, and `completed`: use green for `active` and
  `completed`, amber for `paused`, `blocked`, and `stopped`, grey for role
  states `inactive` and `not started`, an attention color for role state
  `waiting`, light red for role state `failed`, light red for
  `agentbox: no-permissions`, and neutral cyan for both `backend: codex` and
  `backend: claude`. Stop reasons do not change the `stopped` task color;
  failure is conveyed by the affected role's `failed` state. Keep the colors
  readable on Orc's dark-grey status-bar background and do not rely on color
  alone to convey a state.
- `tests/test_orc.py` and Linux PTY/TUI fixtures: cover every rendered task
  status and role state, the no-permissions indicator, the exact colon task
  format, removal of the click-to-focus text, retention of useful key hints,
  right anchoring of the version segment and the documented segment order at
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
  At 120x40 every segment is shown in full. At 80x40 and 80x24 the right rail
  remains fixed, the task and both role segments remain present, the keyboard
  hint is shortened or hidden before those required segments, and backend is
  shortened or hidden before an enabled no-permissions warning. No segment
  wraps, and the task segment remains exactly `<TASK-ID>: <status>`.
- `active` and `completed` are visibly green; `paused`, `blocked`, and
  `stopped` are visibly amber; `inactive` and `not started` are visibly grey;
  `waiting` has a distinct readable attention color; `failed` and
  `agentbox: no-permissions` are visibly light red; and both backend labels
  use the documented neutral cyan style against the dark-grey background.
- Status labels remain explicit and readable when colors are unavailable or
  indistinguishable; styling is an enhancement rather than the only state
  signal. The no-permissions warning remains distinguishable from a failure
  through its label and styling.
- The status bar continues to show both role states, the current task status,
  selected backend, agentbox indicator when enabled, and the retained key
  hints without changing any persisted task state or workflow transition.
- Tests exercise all five persisted task statuses, all five role states,
  normal and stopped workflows, both backend labels, agentbox enabled and
  disabled modes, the 120x40, 80x40, and 80x24 terminal matrix, and the
  rendered order, truncation, alignment, and styling contract through the
  real TUI or an equivalent fixture that verifies the actual composed
  widgets.
- README, workflow documentation, Linux PTY/TUI checks, and clean-diff
  verification pass on the final task commit.
