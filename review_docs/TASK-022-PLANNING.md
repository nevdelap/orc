# Review: TASK-022 planning

## Findings

### R001

Status: ADDRESSED

TASK-022 introduces a process-local input-selection role, but its contract
does not resolve how that role interacts with the existing process-local
scroll target and reserved-key behavior. The current workflow specification
assigns `Tab` to scroll-target cycling, pointer movement to scroll-target
selection, and Page Up/Page Down/Home/End to Orc-owned scrolling, while
keeping Up/Down as prompt-history input. TASK-022 instead assigns `Tab` and
pane clicks to input selection and says that navigation, reserved, and scroll
behavior is preserved without defining the resulting matrix.

Before implementation, specify whether input selection and scroll selection
are separate or coupled; whether Tab and pane clicks update one or both; the
exact handling of Page Up, Page Down, Home, End, Up, Down, Ctrl-Q, Ctrl-R,
mouse events, Shift-Tab, `1`, `2`, and paste when a child is selected or no
child is live; and the deterministic role order used by fallback routing.
Update the task's acceptance criteria and both documentation targets so the
tests have one normative contract. Without this, the implementer must guess
which existing input/scroll behavior the task is allowed to replace.

The current planning amendment does define a key matrix, but it chooses the
wrong product behavior: it explicitly makes input selection and scroll
selection separate. The operator clarification requires one unified
process-local role selection for input, scrolling, highlighting, and Ctrl-R.
R001 remained open until the plan and documentation used that unified model;
the current amendment resolves that specific issue.

Resolution:

- The amended TASK-022, README, and workflow protocol now define one unified
  selected role for input, scrolling, highlighting, and Ctrl-R.
- The task acceptance criteria require the unified target and its sole
  highlight indication to be covered by tests.

### R002

Status: ADDRESSED

The task's selection lifecycle and pane availability do not match the
clarified workflow. The current scope permits Tab and clicks only for live,
non-retired children, treats pointer movement as a separate scroll selection,
updates the input indication after fallback, and forbids Tab changes when no
child is live. This prevents selecting Rufus for Ctrl-R after a terminal
workflow, and it discards the fact that a pane remains available after its
role has launched.

Tell Igor to implement one unified process-local selected role. A role pane is
unavailable only before that role has ever launched; after launch it remains
available for scrolling, highlighting, and Ctrl-R even when its child exits or
is retired. Before the user manually changes it, the selection follows the
active workflow role, including each role handover. Tab or a pane click changes
the unified selection and creates a manual override; the override lasts until
the next role handover, when selection follows the newly active role again.
Pointer movement must not create a second scroll selection. Input fallback
when the selected child is not live must not silently destroy or replace the
unified selection; the task must define the transient write-routing behavior
separately from the retained selected pane.

Resolution:

- The amended task and documentation make panes permanently available after
  first launch, make selection follow handovers until manual override, clear
  that override at the next handover, and keep transient input fallback from
  changing the selected pane or highlight.

### R003

Status: ADDRESSED

The current Ctrl-R contract is incomplete and still launches Igor at round 1
for only paused, blocked, completed, orchestrator-exit, and child-failure
cases. It omits resumable terminal outcomes such as `deadline`, `max_rounds`,
and `manual_pause`, and provides no way to target Rufus. That conflicts with
the intended use after either agent reports completion or the automatic cycle
stops at its maximum and the operator has clarifying input.

Tell Igor to make Ctrl-R available for every valid resumable terminal outcome,
including `max_rounds`, and to target the currently unified selected role. If
Rufus has never launched, its pane is unavailable and cannot be selected; once
it has launched, the user may select either role. The submitted prompt must be
delivered to the selected role with preserved task identity, handoff history,
and prior context. A successful resume must retire remaining children,
preserve the configured limits and audit/history data, start a fresh deadline,
and provide a fresh bounded cycle of up to `max_rounds`. If that fresh cycle
uses round 1, state that round 1 is the new cycle rather than a loss of prior
round history. Define the resulting status, phase, role state, launch, and
handoff behavior for selecting either Igor or Rufus, and cover it in tests and
both documentation targets.

Resolution:

- The amended task and documentation make Ctrl-R target the unified selected
  launched role for every listed resumable terminal outcome, including
  `max_rounds`, preserve context/history, and start a fresh bounded cycle.

### R004

Status: ADDRESSED

TASK-022 is an intentional operator-UX and workflow redesign, not only a
minimal repair to restore bytes to a child PTY. Tell Igor to expand the task
specification and implementation around the complete user experience: one
visible, process-local selected pane is simultaneously the input target,
scroll target, and Ctrl-R target. Its highlight is the sole visible indication
of that unified target. It follows the active role and
each handover until a manual Tab or click override, and the override lasts
until the next handover. Role panes remain available after first launch for
scrolling and resume even when their child is retired; only an as-yet-unstarted
Rufus pane is unavailable. Ctrl-R must be a user-directed continuation for
every resumable terminal outcome, including completion and max-round stops,
with the selected role receiving the prompt and a fresh bounded cycle.

The plan's Goal, Scope, Acceptance criteria, README, workflow protocol, and
real-PTY tests must describe this redesigned interaction end to end: pane
selection and handover transitions, retained panes, prompt ownership and
redirection, role-specific resume, preserved context/history, fresh deadlines
and round budgets, fallback when a selected child is not live, and the
no-live-child behavior. Igor must not implement the existing separate-scroll,
Igor-only Ctrl-R behavior and call the task complete; those are precisely the
UX/workflow behaviors this task is intended to replace.

Resolution:

- The amended Goal, Scope, Acceptance criteria, README, and workflow protocol
  explicitly describe TASK-022 as the complete operator-UX and workflow
  redesign, with real-PTY coverage for the end-to-end behavior.

### R005

Status: ADDRESSED

The amended task still leaves key routing partly implementation-defined by
using `non-reserved navigation`, `navigation keys`, and `control bytes` while
separately reserving Page Up, Page Down, Home, End, Ctrl-Q, Ctrl-R, Tab, and
mouse events. It does not enumerate the complete pass-through versus Orc-owned
matrix, including the behavior of Escape outside the prompt, ordinary control
keys, arrow and other navigation sequences, and paste outside versus inside
the Ctrl-R prompt. The acceptance criteria therefore still permit different
implementations to route the same key differently.

Define one normative key/event matrix in TASK-022 and both documentation
targets, including exact bytes or ownership for every reserved key, all
pass-through text/control/navigation input, mouse events, paste, and the
no-live-child and prompt-open states. Add focused tests for the boundaries.
Igor must not infer that an unspecified key is Orc-owned or child-owned.

The latest amendment explicitly covers Escape, paste, mouse events, and
input-to-bottom visibility, but still leaves `non-reserved navigation`,
`navigation keys`, and `control bytes` undefined in TASK-022, README, and
the then-present summary design document. R005 remained open until those
categories were replaced by one complete normative matrix; the current
amendment resolves that specific issue.

Resolution:

- The amended TASK-022, README, and workflow protocol now enumerate exact
  ownership and bytes for reserved keys, pass-through text/control/navigation,
  Enter, Backspace, Delete, arrows, Shift-Tab, `1`, `2`, paste, mouse events,
  prompt-open input, unknown keys, and no-live-child behavior.
- The acceptance criteria require focused coverage of that complete matrix.

### R006

Status: ADDRESSED

The planning commit adds `design_docs/summary.html`, but TASK-022's Scope and
Acceptance criteria name only `README.md` and
`design_docs/agent_workflow.md`. The new design artifact is therefore outside
the approved task specification and has no required documentation check,
reference, or maintenance contract. It also repeats the unresolved
“non-reserved navigation and paste” category, so it is not an independent
resolution of R005.

Either add `design_docs/summary.html` explicitly to TASK-022's Scope and
Acceptance criteria, require it to stay consistent and pass an applicable
HTML/documentation check, or remove it from the planning commit. Do not leave
an unscoped design artifact in the task baseline.

Resolution:

- `design_docs/summary.html` was removed from the amended planning commit, so
  the final task baseline contains only the scoped README and workflow docs.

## Verification

- `uv run mdformat --check README.md design_docs docs review_docs`: PASS.
- `uv run ruff check .`: PASS.
- `uv run ruff format --check .`: PASS.
- `uv run mypy orc`: PASS.
- `uv run python -c "from pathlib import Path; compile(Path('orc').read_text(), 'orc', 'exec')"`: PASS.
- `uv run python -m compileall -q tests`: PASS.
- `uv run --script orc --help`: PASS.
- `git diff --no-ext-diff --check HEAD^ HEAD`: PASS.
- Commit-message lines are at most 60 characters: PASS.
- All listed checks were rerun against the final amended commit snapshot.

## Final decision

Status: PLANNING_APPROVED

The planning specification is approved. TASK-022 remains `NEW` and is now
eligible for Igor to implement within the complete UX and workflow scope.
