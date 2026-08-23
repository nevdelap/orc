# Review: TASK-010 and TASK-011 planning

## Findings

### R001

Status: ADDRESSED

The planning commit message violates the commit contract: multiple body lines
are longer than 60 columns, including the pending planning-review item. Every
planning commit body line must remain at or below 60 columns and the open item
must identify its review document and finding ID.

Evidence:

- The implementer-owned `Implemented:` bullets in the submitted commit are
  already over 60 columns and must be corrected by the implementer while
  preserving the reviewer-owned findings.

Resolution:

- The corrected planning commit now wraps the implementer-owned bullets and
  the complete commit-message audit passes.

Evidence:

- `git show -s --format=%B HEAD` has no body line over 60 columns.

### R002

Status: ADDRESSED

This planning commit rewrites the specification of the already `COMPLETED`
TASK-009, changing its approved role/backend colors and adding an asserted
operator direction. A planning commit may create or refine a task before its
implementation; it must not retroactively rewrite the completed task's
accepted contract. The commit's `Implemented:` section also does not disclose
these TASK-009 changes. The claimed “Nev explicitly directed” decision has no
operator evidence in this commit or the current planning record.

Required resolution:

- Remove the TASK-009 specification mutation from this planning commit. If a
  new product direction is intended, record it as an explicitly authorized
  new planning change or task with its evidence and review it separately.

Evidence:

- `git diff HEAD^ HEAD -- design_docs/implementation_plan.md` changes lines
  inside the completed TASK-009 entry.
- The parent commit `c0a4be3` is the completed TASK-009 implementation commit.

Resolution:

- The corrected planning diff adds only TASK-010 and TASK-011 after the
  unchanged completed TASK-009 entry; it does not rewrite TASK-009.

Evidence:

- `git diff --no-ext-diff HEAD^ HEAD -- design_docs/implementation_plan.md`
  starts at the new TASK-010 entry.
- The current commit's `Implemented:` section describes only TASK-010 and
  TASK-011.

### R003

Status: ADDRESSED

The planning snapshot fails the required documentation check:
`uv run mdformat --check README.md design_docs docs review_docs` reports that
`design_docs/implementation_plan.md` is not formatted. The added status-order
line is 150 columns, so the planning commit cannot pass its required
documentation gate.

Required resolution:

- Format the documentation tree and rerun the exact check on the corrected
  planning snapshot.

Evidence:

- The exact command fails on the current HEAD.
- `design_docs/implementation_plan.md` line 76 is 150 columns long.

Resolution:

- The corrected planning snapshot is formatted and passes the exact
  documentation check.

Evidence:

- `uv run mdformat --check README.md design_docs docs review_docs`: PASS.

### R004

Status: ADDRESSED

TASK-011's active-agent input contract is not self-contained. It says the
border follows “the one workflow role currently accepting input” and requires
mouse clicks, Tab, Shift-Tab, 1, and 2 to reach that role's PTY, but it does
not define the state-to-role mapping or the mouse protocol. In particular, it
does not say whether click press/release events and coordinates are encoded as
terminal mouse sequences, whether clicks are forwarded while a role is
waiting, or exactly when neither pane is active. Igor would have to invent
these interaction rules and Rufus could not verify them independently.

Required resolution:

- Define the active-agent mapping for implementer/reviewer workflow states and
  the exact forwarding behavior/encoding for each listed input, including
  mouse events.

Evidence:

- TASK-011 Scope and Acceptance criteria use “normal input rules” without
  defining the required mouse or state-transition contract.

Resolution:

- TASK-011 now defines the implementer/reviewer mapping, exact byte and
  sequence forwarding, no-op mouse behavior, and ignored terminal states.

Evidence:

- The corrected Scope and Acceptance criteria specify all listed input
  behavior and the active-agent state mapping.

### R005

Status: ADDRESSED

TASK-011 removes manual mode and changes resume to use the stored directory,
but does not define behavior for existing persisted tasks created under the
current contract. Such records can have `automatic_rounds: false` and may be
paused in the old manual workflow; simply accepting them would preserve a
manual path, while rejecting them would require a specified migration/error.
The automatic-only acceptance criteria cannot be verified for resume without
that compatibility decision.

Required resolution:

- Specify migration, rejection, or explicit compatibility behavior for legacy
  state records, including their automatic-mode flag, backend, and directory.

Evidence:

- Current Orc state persists `automatic_rounds` and the existing resume path
  accepts manual records.
- TASK-011 defines new begin/resume syntax but no legacy-state behavior.

Resolution:

- TASK-011 now specifies migration of missing/false automatic-mode records,
  preservation of task history, defaults and fresh deadline, and rejection of
  invalid target/backend data before mutation.

Evidence:

- The corrected Scope and Acceptance criteria define both legacy migration and
  validation-before-mutation behavior.

## Verification

- `uv run mdformat --check README.md design_docs docs review_docs`: PASS.
- Commit-message body line-length audit: PASS.
- `git diff --no-ext-diff --check HEAD^ HEAD`: PASS.
- No product-runtime gates apply to this planning-only snapshot.

## Final decision

Status: PLANNING_APPROVED

The corrected TASK-010 and TASK-011 specifications are complete, correctly
ordered, and remain `NEW` for implementation.
