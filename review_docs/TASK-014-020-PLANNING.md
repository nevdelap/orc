# Review: TASK-014 through TASK-021 planning

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

Status: ADDRESSED

TASK-018 declares `is_git_repository` to be a boolean, but its failure rule
requires unknown values for failed or malformed Git probes. In particular, a
missing Git executable or a timeout of `git rev-parse` cannot truthfully be
represented as either `true` or `false`; `false` would claim a non-Git target.
Define the field as a boolean-or-unknown value, or provide an explicit
separate failure representation and result matrix for every probe failure.

Resolution:

- TASK-018 now declares `is_git_repository` as boolean-or-`unknown` and
  defines the normal non-Git, empty-repository, detached, and probe-failure
  result matrix.

### R011

Status: ADDRESSED

TASK-019 names `last_handoff`, `accepted_events`, and `rejected_events` but
does not define their field projections or the meaning of “matching events.”
The redaction rule forbids launch tokens, raw payloads, and transcripts, yet
the plan does not say whether `last_handoff` is a summary object, a filtered
canonical handoff, or another shape, nor which audit/rejected event kinds are
included. Specify the exact JSON shapes and per-field redaction/content rules
for both output modes so golden tests have one implementable contract.

Resolution:

- TASK-019 now defines exact `last_handoff`, `accepted_events`, and
  `rejected_events` projections, including source markers, null handling,
  chronological limits, and redaction exclusions.

### R012

Status: ADDRESSED

TASK-014 caps the stored version line at 200 UTF-8 bytes but does not define
whether an over-limit line is truncated, rejected, or replaced with
`unknown`. It also provides no output-size bound for captured `--help` or
`resume --help` transcripts before capability parsing. Define the overflow
behavior and bounded capture size; otherwise a malicious executable can cause
unbounded preflight memory or different compatibility results.

Resolution:

- TASK-014 now defines the 65,536-byte bounded capture, termination and
  diagnostic on overflow, and the rejection/`unknown` behavior for a version
  line over 200 UTF-8 bytes.

### R013

Status: ADDRESSED

The latest planning snapshot fails its required documentation verification.
The new TASK-021 acceptance criteria are followed immediately by the
`## TASK-018` heading without the blank line required by mdformat. The exact
Profile A command fails because `design_docs/implementation_plan.md` is not
formatted, while the parent snapshot formats cleanly. The implementer must
format the plan and rerun the applicable checks on the amended commit.

Evidence:

- `uv run mdformat --check README.md design_docs docs review_docs`: FAIL.
- The parent plan matches `mdformat`; the current plan differs at the missing
  heading separation.

Resolution:

- The heading separation was added. The exact full documentation check now
  passes on the reviewed snapshot.

### R014

Status: ADDRESSED

TASK-017's schema-2 timing migration is not fully specified and conflicts
with its own timing contract. It says every version-2 record migrates, but
only defines `task_started_at` from a “valid existing” `cycle_started_at` and
does not say whether an otherwise valid legacy record with a missing or
malformed value is rejected, migrated with an unavailable timestamp, or
repaired. It also initializes `task_finished_at` to null for every migrated
record, including records already in a terminal status, although the timing
contract defines that field as the current terminal-transition timestamp.
Define the active/terminal and valid/missing legacy cases, including exact
validation, preservation, and unavailable-value behavior, before implementation.

Resolution:

- TASK-017 now requires complete version-2 validation, rejects missing or
  malformed `cycle_started_at`, and explicitly treats terminal legacy
  `task_finished_at: null` as unavailable rather than active.

### R015

Status: ADDRESSED

TASK-017 caps `timing.generations` at 256 and says aggregate totals survive
eviction, but it does not define which records are evicted, whether open
generations are protected, or what happens when no record is evictable. This
leaves serialized timing history and aggregate behavior implementation-defined
and prevents deterministic boundary tests. Specify the retention order,
open-generation rule, and any dropped-generation accounting or rejection
behavior.

Resolution:

- TASK-017 now evicts the oldest ended generation, protects open generations,
  and rejects a full all-open history with a deterministic diagnostic before
  spawning a child.

### R016

Status: ADDRESSED

TASK-021 does not define the exact response schema for
`GET /api/tasks/TASK-ID`. “The same summary plus” timing generations, safe
handoff projections, Git evidence, and the audit timeline leaves their keys,
types, ordering, and redaction shape to inference. It also does not define
the format/types of `generated_at` and `schema_version` or the exact shape of
the dashboard aggregate data. This conflicts with the acceptance requirement
for stable keys and types and prevents unambiguous API-schema/golden tests.
Specify each endpoint's complete JSON object and nested projection schema.

Resolution:

- TASK-021 now defines the collection aggregates, detail-route key order,
  nested generation/handoff/Git/audit projections, timestamp types, and
  redaction rules.

### R017

Status: ADDRESSED

TASK-021 calls the HTTP handling and API payloads bounded, but the selected
state file can contain an unbounded number of task records and `/api/tasks`
has no pagination, task-count cap, or response-size limit. Per-task audit and
generation caps do not bound the aggregate response. Define a finite task
retention/response bound or deterministic pagination/size behavior, including
the corresponding HTML view behavior.

Resolution:

- TASK-021 now bounds the selected task count and both API response sizes,
  defines stable selection order, and specifies deterministic HTTP 413
  behavior without partial data.

### R018

Status: ADDRESSED

TASK-021 contains a contradictory content-type contract: `/` must return a
self-contained UTF-8 HTML page, but the API bullet says “all successful
responses are `application/json`.” Clarify that JSON applies only to API
successes and specify the exact success/error content types for `/` and each
API route so the HTTP tests have one normative contract.

Resolution:

- TASK-021 now assigns explicit HTML and JSON success/error content types to
  the root and API routes.

### R019

Status: ADDRESSED

The TASK-017 migration paragraph contains a duplicated sentence fragment:
after “all other versions are rejected before mutation.” it repeats
“fields, and all other versions are rejected before mutation.” before starting
the timing migration rule. This obscures the schema-migration contract and
should be removed or rewritten as one coherent paragraph.

Resolution:

- The duplicated migration fragment was removed from TASK-017.

### R020

Status: ADDRESSED

TASK-021's new 256-task bound conflicts with its own acceptance criterion
that a browser can view “all retained tasks.” TASK-017 and the existing state
model retain one record per task without a total task-count bound, so a valid
state file can contain more than 256 tasks; TASK-021 then returns HTTP 413
instead of displaying any of them. Define pagination or another complete
bounded view, or change the retention/acceptance contract so every valid
retained task remains viewable.

Resolution:

- TASK-021 now uses fixed-size pagination with stable task ordering and
  exposes every retained task through a page number.

### R021

Status: ADDRESSED

TASK-021 is explicitly read-only and must not migrate state, while TASK-017
allows valid schema-2 records to remain until their migration. TASK-021
mandates API `schema_version: 3` and timing fields but does not define whether
a valid legacy schema-2 state is projected with unavailable timing, rejected
as an invalid web input, or otherwise handled. Specify the exact legacy-read
behavior and ensure it remains non-mutating.

Resolution:

- TASK-021 now defines a non-mutating schema-2 projection, including legacy
  timing, handoff, Git-evidence, and invalid-record behavior.

### R022

Status: ADDRESSED

TASK-021 defines completion, blocked, and stopped rates and “finished-task”
wall-time aggregates but does not define their denominators or which statuses
count as finished, especially for paused and resumed tasks. It also does not
define which persisted activity field determines
`most_recent_task_activity`. Specify these aggregation rules so the required
empty, active, terminal, and resumed fixtures have deterministic results.

Resolution:

- TASK-021 now defines rate denominators, finished statuses, resumed-task
  treatment, and the activity timestamp precedence.

### R023

Status: ADDRESSED

TASK-021 still contradicts itself about the root page's network behavior. It
requires `/` to have “no ... network requests,” but the bounded-view rule says
the root shell follows the paginated `/api/tasks` endpoints until all pages
are loaded. Fetching those endpoints is a network request, even when it is
same-origin and local. Define whether same-origin API fetches are allowed and
state the exact CSP/script contract consistently.

Resolution:

- TASK-021 now explicitly permits only same-origin API fetches, defines the
  inline script and exact CSP, and distinguishes outbound network access.

### R024

Status: ADDRESSED

The pagination bound does not bound the collection response's aggregate
payload: `aggregates.rounds_per_task` is still the complete list for every
task and is repeated on every page. A valid state with enough tasks can make
each page exceed the 1 MiB response limit and return HTTP 413, so the root
cannot load any page and the “every retained task is reachable” guarantee
fails. Bound or paginate the aggregate data independently, or define a
response design that preserves access to all task pages.

Resolution:

- TASK-021 now makes `rounds_per_task` page-local and combines those lists in
  the root, keeping each aggregate payload bounded per page.

### R025

Status: ADDRESSED

The schema-2 web projection says it uses `cycle_started_at` as
`task_started_at` but reports zero elapsed totals for the legacy record. This
is incorrect for an active legacy task: its active `wall_seconds` is defined
by TASK-017 as elapsed time from task start to the current UTC time, and no
terminal timestamp is needed. Define status-sensitive legacy timing so active
records remain truthful while terminal records retain unavailable timing.

Resolution:

- TASK-021 now gives active legacy tasks current wall time from
  `cycle_started_at` while retaining unavailable terminal timing.

### R026

Status: ADDRESSED

The operator clarified that compatibility obligations begin only at the first
public release: private pre-release `v0.0.1` data and behavior do not need to
be supported, and changes made before now are not part of the compatibility
baseline. The current plan nevertheless mandates schema-2 migration in
TASK-017 and schema-2 projections in TASK-021, which treats private historical
data as a required compatibility target. Add an explicit forward-only policy
for Igor: establish the compatibility baseline at the first public release,
do not require migration or projections for pre-baseline history, and require
future public changes to preserve the declared public baseline.

Resolution:

- The plan now establishes a forward-only compatibility policy, identifies
  private `v0.0.1` data as pre-baseline, rejects unsupported pre-baseline
  state, and requires future public changes to preserve the public baseline.

### R027

Status: ADDRESSED

TASK-021 uses the exact redacted `last_handoff` projection defined by
TASK-019, but its Dependencies list only TASK-017. TASK-019 is therefore
allowed to remain incomplete when TASK-021 starts, even though the web
detail response and its handoff list depend on that contract. Add TASK-019
to TASK-021's Dependencies (which also brings in TASK-018 and TASK-020), or
define the complete projection independently in TASK-021 and specify how it
stays consistent with TASK-019.

Resolution:

- TASK-021 now depends on TASK-019, whose dependencies cover TASK-018 and
  TASK-020.

### R028

Status: ADDRESSED

TASK-017 changes the persisted state schema from version 2 to version 3, but
its Scope does not name the normative workflow documentation that still says
new records use schema version 2 in `design_docs/agent_workflow.md`. TASK-021
also adds a user-facing `orc web` command without naming README, CLI-help, or
workflow documentation in Scope. Identify the affected documentation files
and require their updated contracts and checks, so the plan does not permit
an implementation with contradictory protocol docs or an undocumented CLI.

Resolution:

- TASK-017 now scopes the normative workflow protocol update, and TASK-021
  names README.md, design_docs/agent_workflow.md, and the `orc` CLI help,
  with matching documentation acceptance checks.

## Final decision

Status: PLANNING_APPROVED
