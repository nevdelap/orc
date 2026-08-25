# Review: TASK-017

## Findings

### R001

Status: ADDRESSED

The schema validator still accepts records with no `schema_version`. The task
requires schema-2 and every other unsupported record to be rejected before
mutation with `unsupported pre-baseline state schema`, but
`_validate_state_document` permits `version is None` at `orc:439-441` and
continues through the legacy validation path. A record copied from the
pre-schema format therefore loads successfully instead of being rejected.

Evidence:

- A valid schema-3 fixture with `schema_version` and all six audit/timing
  fields removed was passed to `_validate_state_document`; it returned
  `ACCEPTED_MISSING_SCHEMA`.
- `design_docs/implementation_plan.md:167-171` and
  `design_docs/agent_workflow.md:401-405` require unsupported records to be
  rejected and not migrated or launched.

Required resolution:

- Reject missing and unsupported schema versions with the bounded diagnostic
  before any state mutation or launch, and add a regression test for a missing
  `schema_version` record.

Resolution evidence:

- `orc:_validate_state_document` now rejects every version other than 3,
  including a missing version, before required-field validation.
- `tests/test_task017.py:test_missing_schema_is_rejected_before_mutation`
  verifies the mutator is not called and the state bytes are unchanged.
- The full Profile A suite passed with 346 tests.

### R002

Status: ADDRESSED

`last_terminal_event_key` validation checks only tuple syntax and broad enum
membership; it does not enforce the event-specific applicability rules or
consistency with the loaded record. `_validate_terminal_key` at `orc:252-289`
accepts a `child_exit` key with null role and generation, and
`_validate_state_document` at `orc:824-825` accepts that key on an active
record with no corresponding terminal audit event. This can poison an active
record so a later, different terminal event is rejected, while malformed audit
state is treated as loadable.

Evidence:

- `_validate_terminal_key('["child_exit",null,null,"stopped",' '"stopped","deadline"]')` returned successfully.
- An active schema-3 fixture with that key and an empty `audit_events` list
  was accepted by `_validate_state_document`.
- The task acceptance criteria require malformed audit data to be rejected
  before mutation, and the event contract requires `child_exit` to carry a
  role and generation.

Required resolution:

- Validate terminal-key applicability and its relationship to the current
  terminal state/audit evidence; reject impossible or inconsistent keys before
  mutation, with regression coverage.

Resolution evidence:

- `_validate_terminal_key` now checks compact canonical form, event-specific
  role/generation/status/phase/stop-reason applicability, current task state,
  and retained audit evidence.
- `tests/test_task017.py:test_terminal_key_requires_current_state_and_audit_evidence`
  covers active-state, missing-evidence, and valid-evidence cases.

### R003

Status: ADDRESSED

The shared commit message violates the mandatory 60-column body-line limit.
The pending reviewer bullet is 70 characters:
`- [open] review_docs/TASK-017.md R001 - Independent review is pending.`

Evidence:

- `git show -s --format=%B HEAD | awk 'length($0)>60 {exit 1}'` failed.
- The same command reports line 10 at length 70.
- The Commit Contract in `design_docs/agent_workflow.md:633-653` requires
  every body line to be at or below 60 columns.

Required resolution:

- Amend the shared commit message's `Reviewed:` section with wrapped lines,
  preserving the implementer's section and listing all open findings.

Resolution evidence:

- The final message check passed:
  `git show -s --format=%B HEAD | awk 'length($0)>60 {exit 1}'`.

### R004

Status: ADDRESSED

The test fixture globally bypasses the production state validator for every
schemaless record. `tests/test_orc.py:42-52` replaces
`_validate_state_document` with a function that returns such fixtures without
validation. Many existing tests then save, load, resume, and process idle
events using pre-baseline records, so those paths cannot detect a regression
that accepts missing `schema_version` before mutation or launch. The isolated
R001 regression in `tests/test_task017.py` does not cover those workflow paths.

Evidence:

- `validate_legacy_unit_fixture` returns the input unchanged when all task
  records omit `schema_version`.
- The replacement is `autouse=True`, so it applies to the complete
  `tests/test_orc.py` module, including its state and launch tests.
- This is a test-only weakening of the required rejection behavior and
  violates the regression-integrity rule.

Required resolution:

- Remove the validator bypass and update affected fixtures to schema 3, or
  convert each legacy case into an explicit pre-baseline rejection test.

Resolution evidence:

- Every legacy unit-test write now calls an explicit schema-3 fixture helper,
  which delegates to the real `save_state` validator; no validator or save
  function is monkeypatched.
- Legacy malformed-state tests now assert explicit pre-baseline or schema
  rejection.

### R005

Status: ADDRESSED

The deadline transition leaves an open timing generation in a terminal task.
`transition_task` handles `deadline` at `orc:2178-2191` by recording only the
terminal state transition; it does not close any open generation. A direct
schema-3 active record with an open implementer generation remains open after
`transition_task(record, "deadline")`, with `ended_at`, `end_event`, and
`wall_seconds` still null. The polling path invokes this transition while the
workflow is active at `orc:5471-5485`.

Evidence:

- Probe result: after the deadline transition, the record was
  `stopped/stopped/deadline`, while its generation remained open.
- The task requires a generation to end at the first accepted handoff or
  terminal child-exit/cleanup and terminal timing to account for all agent
  time (`implementation_plan.md:196-207`).
- No existing regression test asserts deadline-stop generation closure.

Required resolution:

- Close or otherwise terminally clean up every open generation as part of the
  deadline workflow, preserve aggregate totals, and add a deadline timing
  regression test.

Resolution evidence:

- Deadline transitions call `_close_open_generations` before recording the
  terminal transition.
- `test_deadline_closes_open_generation_and_records_terminal_timing` verifies
  ended time, cleanup event, duration, and aggregate totals.

### R006

Status: ADDRESSED

Terminal-key validation incorrectly requires the matching terminal event to
remain in the rolling audit list. `_validate_terminal_key` raises
`terminal key has no audit evidence` at `orc:319-342` when the event has been
evicted. The specification explicitly says terminal suppression is
independent of rolling event-list eviction, so a valid terminal record must
remain loadable after its terminal event rolls out while its
`last_terminal_event_key` is retained.

Evidence:

- Probe result: a valid `child_exit` terminal key followed by 256 bounded
  non-terminal appends was rejected solely because the terminal event was no
  longer retained.
- `design_docs/implementation_plan.md:228-235` requires eviction-independent
  terminal suppression.
- The current regression test at
  `tests/test_task017.py:343-377` only covers retained evidence and does not
  cover this required eviction boundary.

Required resolution:

- Validate the key against its canonical applicability and current terminal
  state without requiring the evicted event to remain in the rolling list, and
  add an eviction regression test.

Resolution evidence:

- `_validate_terminal_key` now checks canonical shape and current state only;
  retained audit evidence is not required.
- `test_terminal_key_requires_current_state_and_survives_eviction` verifies a
  valid key remains loadable after its event is evicted.

### R007

Status: ADDRESSED

The state validator accepts a terminal schema-3 record with no terminal audit
event, no terminal key, and no finished timing. At `orc:878-898`, the checks
for terminal evidence and `task_finished_at` are conditional on `audit_events`
being non-empty. A stopped record initialized with an empty audit list is
therefore accepted, even though every terminal transition must be explained
by an atomic terminal audit event and terminal timing record.

Evidence:

- Probe result: a `stopped/stopped/deadline` schema-3 record with
  `audit_events: []`, `last_terminal_event_key: null`, and
  `task_finished_at: null` returned `ACCEPTED` from
  `_validate_state_document`.
- The task requires exact event applicability and terminal timing, and says
  malformed audit data is rejected before mutation (`implementation_plan.md: 211-235, 247-255`).
- Several schema-3 test fixtures use this invalid terminal shape, masking the
  missing invariant.

Required resolution:

- Require terminal records to carry a valid terminal key/evidence or otherwise
  reject them before mutation, and add a regression test for the empty-history
  terminal boundary.

Resolution evidence:

- Schema-3 terminal records now require a current valid terminal key and a
  finished timing record, even with an empty audit list.
- `test_terminal_and_revision_boundaries_are_rejected` covers missing-key and
  missing-finished-timing rejection.

### R008

Status: ADDRESSED

The schema-3 validator accepts `revision: null`, although the durable protocol
requires a monotonically increasing integer revision. `orc:495-501` validates
the revision only when it is non-null. The record then reaches mutation, where
`mutate_task_state` attempts `None + 1` at `orc:1040-1043` and fails with a
type error instead of rejecting the malformed state before mutation or launch.

Evidence:

- Probe result: a complete schema-3 record with `revision: null` returned
  `ACCEPTED` from `_validate_state_document`.
- `design_docs/agent_workflow.md:397-405` requires a monotonically increasing
  revision and complete record validation.

Required resolution:

- Require a non-boolean integer revision in schema-3 records and add a
  before-mutation regression test.

Resolution evidence:

- Revision validation is unconditional for schema-3 records and rejects null,
  booleans, non-integers, and negative values.
- `test_schema3_rejects_invalid_revision_before_required_fields` covers the
  before-mutation boundary.

### R009

Status: ADDRESSED

The mandatory Profile A coverage gate was below its required threshold because
pre-schema compatibility branches were unreachable after schema-3 validation,
and several parser boundary paths lacked regression coverage.

Evidence:

- The command previously reported `349 passed` and 83.84% coverage.

Required resolution:

- Remove unreachable pre-schema launch/resume compatibility paths and add
  boundary tests for Claude results and raw idle-hook streams.

Resolution evidence:

- The exact coverage command now reports 351 passed and 90.43% coverage.
- Schema-3 validation remains the only state-load baseline; unsupported
  pre-schema records are still rejected before launch or mutation.

## Verification

- `uv sync --locked`: PASS.
- `uv run pytest -q`: PASS (351 tests).
- `uv run pytest -q -m integration tests`: PASS (53 tests).
- `uv run pytest -q --cov=orc --cov-branch --cov-report=term-missing --cov-report=xml:coverage.xml --cov-fail-under=90`: PASS (351 tests, 90.43% coverage).
- `uv run ruff check .`: PASS.
- `uv run ruff format --check .`: PASS.
- `uv run mypy orc`: PASS.
- `uv run python -c "from pathlib import Path; compile(Path('orc').read_text(), 'orc', 'exec')"`: PASS.
- `uv run python -m compileall -q tests`: PASS.
- `uv run --script orc --help`: PASS.
- `uv run mdformat --check README.md design_docs docs review_docs`: PASS.
- `git diff --no-ext-diff --check HEAD^ HEAD`: PASS.
- `git show -s --format=%B HEAD | awk 'length($0)>60 {exit 1}'`: PASS.
- `git status --short --branch`: PASS; clean worktree.

## Final decision

Status: COMPLETED

R001-R009 are addressed in the shared task commit. The current re-review found
no additional material issues.
