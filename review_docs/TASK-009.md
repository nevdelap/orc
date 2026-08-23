# Review: TASK-009

## Findings

### R001

Status: ADDRESSED

The planning commit's pending `Reviewed:` item does not identify a review
document or finding ID. The commit contract requires an open planning-review
item to identify the review record while the independent review is pending.

Resolution:

- The reviewer-owned `Reviewed:` section now identifies this document and
  finding ID and records the resolved planning findings.

Evidence:

- `git show -s --format=%B HEAD` after amendment contains traceable
  `review_docs/TASK-009.md` entries and preserves the implementer's section.

### R002

Status: ADDRESSED

TASK-009 requires semantic styling for every rendered task status, but its
mapping omits the persisted `stopped` task status. The current implementation
persists `active`, `paused`, `blocked`, `stopped`, and `completed`; `stopped`
is produced for deadline, max-round, child-failure, and manual-pause stops.
The plan assigns colors to `active`, `completed`, `paused`, and `blocked`, but
does not define the required styling for `stopped` or whether its stop reason
changes that styling. Igor cannot satisfy “every task status” and Rufus cannot
verify it without this product decision.

Required resolution:

- Define the complete persisted task-status set and the semantic styling for
  `stopped`, including whether stop reasons share one style or differ.

Evidence:

- `orc:set_stop_reason` maps non-completion, non-clarification stops to
  `status = "stopped"`.
- TASK-009 Scope and Acceptance criteria enumerate no `stopped` styling.

Resolution:

- TASK-009 now enumerates `active`, `paused`, `blocked`, `stopped`, and
  `completed`, assigns amber to `stopped`, and specifies that stop reasons do
  not alter its task color.

Evidence:

- `design_docs/implementation_plan.md` names all five persisted task statuses
  and tests all five rendered values.

### R003

Status: ADDRESSED

The plan requires the version segment to remain anchored at every “supported
terminal size” and asks for wide and constrained size coverage, but it does
not define the supported terminal environment or size matrix. The current UI
has distinct side-by-side, stacked, and single-pane thresholds, and prior UI
work used 120x40, 80x40, and 80x24. TASK-009 does not state whether those are
the required sizes, whether the 80x24 minimum is inclusive, or whether tiny
terminals are in scope. The acceptance evidence is therefore not reproducible.

Required resolution:

- Pin the Linux terminal environment and exact supported size matrix,
  including which layout thresholds and constrained/tiny cases are required.

Evidence:

- TASK-009 Scope and Acceptance criteria say “supported terminal sizes” but
  define no dimensions or environment.
- `orc:update_layout` has separate side-by-side, stacked, and single modes.

Resolution:

- TASK-009 now pins Linux `xterm-256color` at 120x40, 80x40, and 80x24,
  identifies each layout mode, and excludes terminals smaller than 80x24.

Evidence:

- The exact matrix and its required tests are stated in the task Scope and
  Acceptance criteria.

### R004

Status: ADDRESSED

TASK-009 says the status-bar information order must be documented and calls
for a stable left/right layout, but neither the plan nor the acceptance
criteria specifies the required segment order. The acceptance criteria only
list the information that must remain present, allowing materially different
layouts while still appearing compliant. This leaves a product decision for
Igor to invent and prevents an exact rendered-widget review.

Required resolution:

- Specify the exact left-to-right segment order, truncation rules, and the
  right-anchored version boundary to be documented and tested.

Evidence:

- TASK-009 Scope requests documentation of “status-bar information order”
  without stating that order.
- The existing `orc:status_text` order is not made an immutable contract by
  the task.

Resolution:

- TASK-009 now fixes the left-to-right order, the fixed right version rail,
  the required segments, and constrained-width priority rules.

Evidence:

- The task requires tests for order, truncation, alignment, and the exact
  120x40, 80x40, and 80x24 matrix.

### R005

Status: ADDRESSED

The Scope requires semantic styling for backend text, but the color mapping in
Scope and Acceptance criteria covers task states, role states, and the
agentbox warning only. It does not define how the selected backend text is to
be styled or how that styling is verified. A default/unsemantic backend label
could therefore satisfy the listed color assertions while violating Scope.

Required resolution:

- Define the backend values and their required styling, or explicitly state
  that backend text uses a neutral style and remove the broader requirement.

Evidence:

- TASK-009 Scope names backend styling but gives no backend color or semantic
  category.
- TASK-009 Acceptance criteria contain no backend-style assertion.

Resolution:

- TASK-009 now defines `backend: codex` and `backend: claude` and requires a
  documented neutral-cyan style and rendered-widget assertion for both.

Evidence:

- The task Scope and Acceptance criteria explicitly require both backend
  labels and their neutral-cyan styling.

### R006

Status: ADDRESSED

The fixed right rail is not actually protected when the agentbox warning is
enabled. At 120x40 `_visible_status_keys` always enables task, both roles,
backend, agentbox, and the full hint, while `#status-left` is only the width
remaining after the 10-column version rail and clips overflow. In a real
Textual run with the Linux agentbox marker and the Codex no-permissions flag,
the left rail measured 110 columns, but the hint occupied x=99 through x=134
while the version rail occupied x=110 through x=120. The full hint therefore
cannot be shown and overlaps the fixed rail, violating the 120x40 requirement
that every segment be shown in full and the right rail remain fixed. The same
implementation keeps the enabled warning and all required role segments at
80x40/80x24 without accounting for their rendered widths, so long explicit
role labels can also run into the version rail.

Evidence:

- `orc` lines 851-855 make the left rail a 1fr container with hidden
  overflow, and lines 1068-1072 force every optional segment visible at
  widths of 120 or more.
- `orc` lines 1134-1146 only toggle display; they do not reserve space or
  prevent the child widgets from extending beyond the left rail.
- A real `OrcApp.run_test(size=(120, 40))` run with `agentbox: no-permissions`
  enabled reported `status-left` width 110, `status-agentbox` at x=73 width
  26, `status-hint` at x=99 width 35, and `status-version` at x=110 width 10.

Resolution:

- Igor removed the wide-layout gutters when the warning is present, measures
  the rendered segment widths, and hides only optional content that cannot fit.
  The new real-TUI boundary fixture now verifies the warning, hint, and
  required segments stay before the fixed version rail at 120x40, 80x40, and
  80x24.

### R007

Status: ADDRESSED

The added tests do not provide the required rendered-widget coverage. The
task requires all five task statuses and all five role states to be checked
through the real TUI or an equivalent fixture, including rendered order,
alignment, and styling. The task-status parameterization only calls
`status_segments` and the private color lookup; the role-state parameterization
only calls the same lookup; and the backend test compares constants. The sole
real TUI styling assertion covers one active task at 120x40. The matrix test
checks display flags but does not assert the composed order, widget widths, or
right-rail non-overlap, which is why R006 passed the suite.

Evidence:

- `tests/test_orc.py` lines 2224-2263 test mappings without rendering the
  status widgets.
- `tests/test_orc.py` lines 2290-2371 cover one active/codex scenario and
  visibility toggles, but do not assert all statuses, role styles, exact
  rendered order, or alignment boundaries.

Resolution:

- `tests/test_orc.py` now renders all five task statuses, all five role
  states, both backends, the agentbox warning, label/value styles, segment
  boundaries, and the supported terminal matrix through Textual widgets.

Evidence:

- `tests/test_orc.py` lines 2382-2553 provide the expanded real-TUI fixture;
  the full suite passes with 126 tests.

### R008

Status: ADDRESSED

The constrained-width priority rule still drops an enabled no-permissions
warning when the required labels are too long, then restores backend text.
This violates the acceptance criteria that the warning remains shown when
enabled and that backend yields to it. In a real Linux-marker run at 80x24
with a persisted completed task whose launch command includes the Codex
no-permissions flag, `agentbox_enabled(record)` returned `True`, but
`_visible_status_keys` returned task, both roles, and backend; the warning
widget was `display=none` while `backend: codex` was displayed. Completed
tasks are a supported workflow state, so this is not only a synthetic
pre-launch case.

Evidence:

- `orc` lines 1094-1100 explicitly remove `agentbox` when `used(visible) > width`, then add backend if it fits.
- A real `OrcApp.run_test(size=(80, 24))` run with `status=completed`,
  `phase=complete`, the agentbox marker, and the persisted flag reported
  `agentbox_enabled=True`, `status-agentbox` hidden, `status-backend` shown,
  and the version rail fixed at x=70..80.
- `design_docs/implementation_plan.md` requires the indicator to remain
  present when enabled and requires backend to yield to it.

Resolution:

- Igor now retains the enabled warning widget and suppresses backend text in
  the completed 80x24 scenario. The updated real-TUI fixture asserts that
  visibility and the full suite passes with 126 tests.

### R009

Status: ADDRESSED

The implementation commit changes the approved TASK-009 product contract in
`design_docs/implementation_plan.md`: waiting changes from a distinct
attention color to grey, and both backend labels change from neutral cyan to
white. Those changes are outside the implementation Scope, which only permits
the plan's task-state transition, and they contradict the planning resolution
recorded in R005. Igor must not silently narrow or redesign an approved task;
the plan/operator must resolve such a product decision before implementation.

Evidence:

- The planning baseline `e4f5bfd` specifies an attention color for `waiting`
  and neutral cyan for both backend labels.
- The current task commit changes those requirements to grey and white in
  `design_docs/implementation_plan.md` and updates README/workflow docs to
  match.
- `docs/roles.md` and `design_docs/agent_workflow.md` require the plan to be
  the source of truth and prohibit silently narrowing or guessing product
  decisions.

Resolution:

- Nev's explicit product direction is now recorded in the task Scope and was
  accepted by the operator in this review context. The current plan therefore
  intentionally specifies grey for `waiting` and white for both backend
  labels; this is an authorized plan change rather than an Igor guess.

### R010

Status: ADDRESSED

### R010

Status: OPEN

The new width handling preserves widget placement by clipping status content,
and it still shortens a required wide-layout segment. In the supported
completed-task state with agentbox enabled, a real 80x24 run gives the warning
widget a 13-column region even though its rendered content is 27 columns
(` · agentbox: no-permissions`); `.status-segment` has `overflow: hidden`, so
the no-permissions value is cut off in the terminal. The same state at 120x40
returns `Tab · Ctrl-Q` instead of the required full
`Tab switches panes · Ctrl-Q exits`, despite the acceptance criterion that
every 120x40 segment be shown in full. The constrained rules permit shortening
or hiding the keyboard hint and backend, but do not permit shortening the
agentbox warning; the wide rule permits no shortening at all.

Evidence:

- `orc` lines 858-864 set every status segment to `overflow: hidden`, and
  lines 1160-1174 assign the warning a width of 13 at 80x24 while retaining
  its 27-column content.
- A real `OrcApp.run_test` with Linux marker, completed task, and persisted
  Codex no-permissions flag reported at 120x40:
  `status-hint` = ` · Tab · Ctrl-Q`; at 80x24:
  `status-agentbox` region x=54, width=13, content
  ` · agentbox: no-permissions`.
- `tests/test_orc.py` lines 2518-2558 assert widget text and boundaries but
  do not assert the rendered region is wide enough for the content or that
  the full 120x40 hint is retained.

Resolution:

- The operator explicitly changed R010's contract to permit clipping any
  overflowing left-side content while always reserving a separating space and
  the complete version segment. The implementation now gives the version
  rail 11 cells, renders ` orc v0.0.1` in that rail, and leaves the left
  container at the remaining width with overflow hidden.

Evidence:

- A real Linux `xterm-256color` Textual run with the completed agentbox state
  measured the version rail as x=109, width=11 at 120x40 and x=69, width=11
  at both 80x40 and 80x24. In every case its rendered text was the complete
  ` orc v0.0.1`; left-side widgets were clipped only at the left-container
  boundary.
- `tests/test_orc.py` now asserts the 11-cell right rail, its complete text,
  the left boundary, and the supported size matrix.

## Planning verification

- `uv run mdformat --check README.md design_docs docs review_docs`: PASS.
- `git diff --no-ext-diff --check HEAD^ HEAD`: PASS before final amendment.
- No product-runtime gates apply to this planning-only snapshot.

## Planning final decision

Status: PLANNING_APPROVED

The corrected TASK-009 specification is complete and remains `NEW`, making it
eligible for Igor to implement.

## Verification

- `TERM=xterm-256color uv run pytest -q`: PASS (125 tests).
- `uv run pytest -q`: PASS (125 tests).
- `uv run --script orc --help`: PASS.
- `uv run python -m py_compile orc tests/test_orc.py`: PASS.
- `uv run mdformat --check README.md design_docs docs review_docs`: PASS.
- `git diff --no-ext-diff --check HEAD^ HEAD`: PASS before this review
  amendment.
- Worktree was clean before this review amendment.
- `TERM=xterm-256color uv run pytest -q`: PASS (126 tests) on the current
  implementation snapshot.
- `uv run --script orc --help`: PASS.
- `uv run python -m py_compile orc tests/test_orc.py`: PASS.
- `uv run mdformat --check README.md design_docs docs review_docs`: PASS.
- `git diff --no-ext-diff --check HEAD^ HEAD`: PASS before this review
  amendment.

## Final decision

Status: COMPLETED

All findings are addressed. TASK-009 is approved for completion.
