# Review: Orc follow-up task planning

## Findings

### R001

Status: ADDRESSED

Independent planning review is pending for TASK-004, TASK-005, and TASK-006.

The planning commit defines the bundled PTY/UI, workflow-control, and Claude
Code backend tasks. Rufus must verify that each task has complete Goal,
Dependencies, Scope, and Acceptance criteria, that the dependencies are
ordered correctly, and that the proposed five-round and 60-minute limits are
explicit and testable.

Resolution:

- TASK-004, TASK-005, and TASK-006 each contain Goal, Dependencies, Scope, and
  Acceptance criteria sections.
- Dependencies form the explicit order TASK-003 -> TASK-004 -> TASK-005 ->
  TASK-006, and TASK-003 is already `COMPLETED`.
- TASK-005 explicitly states the five-round maximum and 60-minute default.

Evidence:

- `design_docs/implementation_plan.md` contains all three complete task
  specifications and the dependency chain.

### R002

Status: ADDRESSED

TASK-004 has been expanded to cover the complete operator-facing UI rather
than only resize and key handling. It requires iterative manual testing by
Nev at startup, interaction/resize, and end-to-end shutdown checkpoints, with
the tested commit, scenario, observations, and fixes recorded before review.
However, Nev is not a role defined by `docs/roles.md` or the workflow, and the
plan does not define Nev's authority, environment, exact scenarios, evidence
artifact, or pass/fail criteria. It also leaves "both layout modes" and
"supported sizes" undefined. Igor cannot satisfy or Rufus independently verify
this protocol without inferring those product and test decisions.

Required resolution: define Nev and the manual-validation evidence protocol,
including exact environments, scenarios, artifacts, and pass/fail criteria;
define the supported layout modes and terminal-size matrix, or remove the
undefined manual and layout requirements.

Resolution:

- TASK-004 defines Nev as the human operator and acceptance tester, specifies
  a Linux `xterm-256color` environment with `uv` and Codex, and defines the
  120x40 side-by-side, 80x40 stacked, and 80x24 single-pane matrix.
- It requires exact startup, focus/input/resize, handoff, and shutdown
  scenarios, records commit/environment/scenario/observation/pass-fail data
  in `review_docs/TASK-004.md`, and makes failed checkpoints blocking.

Evidence:

- `design_docs/implementation_plan.md` contains the manual protocol, matrix,
  evidence fields, and checkpoint acceptance criteria.

### R003

Status: ADDRESSED

TASK-005 requires an explicitly enabled automatic-cycle mode and an explicit
pre-run way to choose a deadline or round limit, but it does not name the CLI
option, configuration key, command syntax, default behavior, or persisted
state fields used to enable and configure that mode. “Explicitly enabled” is
not sufficient for a self-contained task specification; the implementation
would otherwise have to invent the operator interface.

Evidence:

- TASK-005 Scope says to add an automatic-cycle mode and a pre-run limit
  choice, but names no option, configuration file, or command form.
- Its Acceptance criteria verify automatic mode behavior but do not specify
  how a user enables it or selects a non-default limit.

Required resolution: specify the exact enable/configuration interface, its
default-off behavior, accepted limit values, and the corresponding persisted
state fields and tests.

Resolution:

- TASK-005 defines `--auto`, `--max-rounds N` from 1 through 5, and
  `--deadline-minutes N` from 1 through 1440, with defaults of 5 and 60.
- It defines default-off behavior, invalid combinations, resume reuse, and
  the persisted settings and deadline fields.

Evidence:

- `design_docs/implementation_plan.md` specifies the exact begin command,
  option ranges, persisted keys, and corresponding acceptance tests.

### R004

Status: ADDRESSED

TASK-006 does not specify the Claude Code backend contract sufficiently for an
independent implementation or review. It names no backend selector or value,
Claude executable/command and arguments, environment variables, supported
Claude mode/version, session identity format, or resume invocation. The Scope
only says to make these details explicit, leaving the product interface for
Igor to invent.

Evidence:

- TASK-006 requires "explicit Claude Code selection" and says command,
  environment, session identity, and resume behavior must be explicit, but
  supplies none of those values.
- Acceptance criteria refer to the implemented Linux command line and
  configuration without defining the expected command line or configuration.

Required resolution: define the backend selector, Claude command and
arguments, environment/configuration, supported mode/version, session and
resume contract, and exact README/test evidence.

Resolution:

- TASK-006 defines `--backend codex|claude`, Codex as the default, and
  persisted selection on resume.
- It defines `ORC_CLAUDE_COMMAND` with `claude` as the default, print mode,
  exact stream/input flags, capability probing, initial and resume commands,
  session fields, and fake-backend test evidence.

Evidence:

- The [Anthropic CLI reference](https://docs.anthropic.com/en/docs/claude-code/cli-usage)
  documents the specified print, output-format, input-format, and resume
  flags and session-resume usage.
- `design_docs/implementation_plan.md` specifies the selector, commands,
  capability probe, state fields, and acceptance coverage.

## Verification

- `git diff --no-ext-diff --check HEAD^ HEAD`: PASS.
- Commit subject and body lines are at or below 60 characters: PASS.
- TASK-003 is `COMPLETED`; TASK-004, TASK-005, and TASK-006 remain valid
  `NEW` tasks with the required dependency order.
- No product-runtime gates were applicable because this planning diff changes
  no application source or tests.

## Final decision

Status: PLANNING_APPROVED
