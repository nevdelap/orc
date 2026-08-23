# Review: TASK-012 planning

## Findings

### R001

Status: ADDRESSED

TASK-012 refers to “every supported terminal size” but does not make the
terminal/platform matrix self-contained. Its test bullet names 120x40, 80x40,
and 80x24 but omits the required Linux `xterm-256color` environment and does
not state that terminals smaller than 80x24 are outside the contract. The
planning rules require each requested platform and variant, plus evidence for
each scope item, to be explicit before implementation.

Required resolution:

- State the exact Linux `xterm-256color` matrix of 120x40, 80x40, and 80x24
  in Scope and Acceptance criteria, including the out-of-scope smaller-size
  boundary and real-TUI evidence at each size.

Resolution:

- TASK-012 now states the Linux `xterm-256color` matrix, the smaller-terminal
  boundary, and the required matrix evidence in both Scope and Acceptance
  criteria.

### R002

Status: ADDRESSED

The scrollback requirement is not testable because “retain sufficient
per-pane scrollback” specifies neither a minimum retained history nor an
unbounded/capped policy. An implementation could retain too little history or
discard old lines at an unspecified point while still claiming compliance.
The plan also does not define what happens when a cap is reached.

Required resolution:

- Choose and state an exact retention policy, such as an unbounded history or
  a minimum line capacity, and define the oldest-line behavior at the limit.
  Add acceptance evidence that demonstrates output older than the viewport
  remains independently navigable for both panes.

Resolution:

- TASK-012 now requires at least 10,000 logical lines per pane, specifies
  oldest-line eviction and Home behavior at the cap, and requires evidence
  for output older than the viewport and the cap.

### R003

Status: ADDRESSED

“Terminal state” is not an explicit state contract for `Ctrl-R`. The existing
workflow has distinct persisted statuses and stop reasons, including
`paused`, `blocked`, `stopped`, and `completed`, but TASK-012 does not say
which of them enable the follow-up prompt or how inconsistent role/phase data
is handled. The implementer would have to infer when `Ctrl-R` is consumed,
ignored, or allowed to launch Igor.

Required resolution:

- Enumerate the exact eligible statuses and require both role states to be
  `inactive`; define the no-op behavior for `active` and any other status, and
  include each eligible status in the acceptance evidence.

Resolution:

- TASK-012 now enumerates `paused`, `blocked`, `stopped`, and `completed`,
  requires inactive roles, defines inconsistent-state no-op behavior, and
  requires evidence for every eligible status.

### R004

Status: ADDRESSED

The in-place resume contract does not specify the persisted state transition.
“Preserves task history” and “preserves ... configured round/deadline limits”
do not say which fields are retained versus reset for the new cycle. In
particular, the plan leaves `stop_reason`, failure/blocker metadata, role
session IDs and generations, `phase`, `status`, `cycle_started_at`, and
`deadline_at` ambiguous. It also does not state whether submission starts a
fresh deadline or how completed children are retired before Igor relaunches.

Required resolution:

- Define the exact retained and reset fields, including history append/reset
  behavior, stale failure cleanup, role-session retirement, active
  implementer state, and fresh-cycle/deadline timestamps. Add acceptance
  assertions proving the specified state before and after submission.

Resolution:

- TASK-012 now specifies retained identity/configuration and handoff history,
  request append behavior, terminal-metadata cleanup, child retirement,
  active implementer state, round reset, and fresh cycle/deadline timestamps.

### R005

Status: ADDRESSED

The `Ctrl-R` eligibility contract conflicts with the existing role-state
contract for child failures. TASK-012 lists every `stopped` record as eligible
but also requires both rendered role states to be `inactive`. The existing
implementation renders the role named by `child_failure` as `failed`, so a
stopped child-failure record can satisfy the status condition but can never
satisfy the role condition. The plan does not say whether child-failure
recovery is intended or is an explicit no-op.

Required resolution:

- Explicitly choose the child-failure behavior. If it is resumable, allow the
  documented `failed` role state and specify its reset before relaunch; if it
  is not resumable, exclude `child_failure` from the eligible cases and add a
  no-op acceptance test for it.

Resolution:

- TASK-012 explicitly permits the `stopped`/`child_failure` case when exactly
  one role is `failed` and the other is `inactive`; it clears failed-role and
  child-failure metadata before starting the new implementer cycle.

Evidence:

- The Scope and Acceptance criteria specify the exact child-failure role
  combination, reset behavior, and dedicated test coverage.

## Final decision

Status: PLANNING_APPROVED

TASK-012 is complete as a planning specification and remains `NEW`, eligible
for Igor to implement after the dependency reaches `COMPLETED`.
