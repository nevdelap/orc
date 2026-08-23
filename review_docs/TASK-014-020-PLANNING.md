# Review: TASK-014 through TASK-020 planning

## Findings

### R001

Status: ADDRESSED

The independent planning review is complete. The findings below record the
material specification gaps found in TASK-014 through TASK-020.

Resolution:

- The review was performed against the complete planning commit and its
  parent, the active workflow protocol, and the repository verification
  commands.

### R002

Status: ADDRESSED

The plan now defines Verification Profiles A and B with exact Linux commands,
coverage options, report path, failure threshold, applicability, and the
conditional dependency/security checks. Each task requires the profile result
in its handoff and review document.

Resolution:

- The shared verification profile block was added to
  `design_docs/implementation_plan.md`.

### R003

Status: ADDRESSED

TASK-014 now explicitly normalizes invalid UTF-8 with U+FFFD and treats it as
non-failing, while retaining deterministic failure behavior for non-zero,
timeout, and `OSError` results.

Resolution:

- The preflight output-decoding rule was made explicit in the task scope.

### R004

Status: ADDRESSED

TASK-015 and the workflow protocol now specify stopped status/phase,
diagnostics, inactive-role requirements, and CLI/in-place resume behavior for
`orchestrator_exit`.

Resolution:

- The `orchestrator_exit` stop-reason and resume rules were added to the
  task scope and `design_docs/agent_workflow.md`.

### R005

Status: ADDRESSED

TASK-016 now permits the trusted built-in role and handoff-format prompts,
explicitly separates them from bounded operator and handoff data, and caps
the stream dropped-event counter with saturation behavior.

Resolution:

- The prompt boundary and `stream_dropped_count` rules were made explicit in
  the task scope.

### R006

Status: ADDRESSED

TASK-017 now specifies schema version 3, the bounded dropped counter, the
persisted terminal-event key and its type/initial value, the exact terminal
event kinds, the pre-TASK-018 null commit value, and the UTF-8 byte limit for
`detail`.

Resolution:

- The remaining audit fields, bounds, validation, and deduplication rules
  were added to the task scope.

### R007

Status: ADDRESSED

TASK-018 now consistently uses `null` for non-Git cleanliness, distinguishes
detached HEAD from symbolic-ref failure, and omits overlong paths while
setting the truncation flag.

Resolution:

- The Git evidence result matrix and overflow behavior were made explicit in
  the task scope.

### R008

Status: ADDRESSED

TASK-019 now specifies exact default labels, JSON keys and order, absent-value
representations, event limits, exit codes, and a dependency on TASK-020 for
activity data.

Resolution:

- The stable output schema and TASK-020 dependency were added to the task.

### R009

Status: ADDRESSED

TASK-020 now specifies the per-role activity schema, UTC and monotonic clock
roles, initial values, age calculation, event ordering, debounce retry, and
invalid-record diagnostic behavior.

Resolution:

- The activity and clock contract was added to the task scope.

### R010

Status: OPEN

TASK-018 declares `is_git_repository` to be a boolean, but its failure rule
requires unknown values for failed or malformed Git probes. In particular, a
missing Git executable or a timeout of `git rev-parse` cannot truthfully be
represented as either `true` or `false`; `false` would claim a non-Git target.
Define the field as a boolean-or-unknown value, or provide an explicit
separate failure representation and result matrix for every probe failure.

### R011

Status: OPEN

TASK-019 names `last_handoff`, `accepted_events`, and `rejected_events` but
does not define their field projections or the meaning of “matching events.”
The redaction rule forbids launch tokens, raw payloads, and transcripts, yet
the plan does not say whether `last_handoff` is a summary object, a filtered
canonical handoff, or another shape, nor which audit/rejected event kinds are
included. Specify the exact JSON shapes and per-field redaction/content rules
for both output modes so golden tests have one implementable contract.

### R012

Status: OPEN

TASK-014 caps the stored version line at 200 UTF-8 bytes but does not define
whether an over-limit line is truncated, rejected, or replaced with
`unknown`. It also provides no output-size bound for captured `--help` or
`resume --help` transcripts before capability parsing. Define the overflow
behavior and bounded capture size; otherwise a malicious executable can cause
unbounded preflight memory or different compatibility results.

## Final decision

Status: REVIEWED_FOUND_ISSUES
