# Review: TASK-009 planning

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

## Verification

- `uv run mdformat --check README.md design_docs docs review_docs`: PASS.
- `git diff --no-ext-diff --check HEAD^ HEAD`: PASS before final amendment.
- No product-runtime gates apply to this planning-only snapshot.

## Final decision

Status: PLANNING_APPROVED

The corrected TASK-009 specification is complete and remains `NEW`, making it
eligible for Igor to implement.
