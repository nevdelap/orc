# Implementation Plan

This file is the task source of truth for planned project work.

Before starting a new change, add a `NEW` task under `Tasks`. The shared state
transitions, commit contract, handoff procedures, review-document format, and
verification workflow are defined in `design_docs/agent_workflow.md`; role
responsibilities are defined in `docs/roles.md`.

Public compatibility is forward-only. The private pre-release `v0.0.1` is not
a public compatibility baseline, but that exception does not permit an
implementation task to strand state that exists in the shared workspace or
that the preceding task produced. Every schema change must remain readable at
each intermediate commit and between tasks: introduce new fields and readers
first, keep deprecated representations readable while they are being
converted, and remove them only in a later task after no writer emits them.
Any explicit migration must be atomic, repeatable, validated, and preserve a
recoverable backup. Every task that changes a schema must name this
compatibility/deprecation plan and test the partially migrated and
between-task states. Unsupported pre-baseline state may be rejected only when
the established conversion path cannot strand in-use state; a schema update
must never be the reason the current workflow becomes unloadable.

## Tasks

### Verification profiles

Every task in this plan must record the results of Verification Profile A in
its handoff and review document. Tasks whose Scope includes real PTY, child
process, or TUI lifecycle behavior must also run Profile B. These are the
exact Linux commands for the profiles:

- Profile A:
  `uv sync --locked`
- Profile A:
  `uv run pytest -q --cov=orc --cov-branch --cov-report=term-missing --cov-report=xml:coverage.xml --cov-fail-under=90`
- Profile A:
  `uv run ruff check .`
- Profile A:
  `uv run ruff format --check .`
- Profile A:
  `uv run mypy orc`
- Profile A:
  `uv run python -c "from pathlib import Path; compile(Path('orc').read_text(), 'orc', 'exec')"`
- Profile A:
  `uv run python -m compileall -q tests`
- Profile A:
  `uv run --script orc --help`
- Profile A:
  `uv run mdformat --check README.md design_docs docs review_docs`
- Profile A:
  `git diff --no-ext-diff --check HEAD^ HEAD`
- Profile A:
  `git show -s --format=%B HEAD | awk 'length($0)>60 {exit 1}'`
- Profile B:
  `uv run pytest -q -m integration tests`

`uv run pip-audit --strict` and
`actionlint .github/workflows/ci.yml` are not applicable unless a task's final
diff changes dependencies or workflow files; if it does, both commands become
required evidence. A passing result is valid only for the exact final commit
snapshot under review.

## TASK-021 - Serve historical task analytics

State: NEW

Goal:

- Provide a safe local web view of completed and active Orc tasks, including
  timing, rounds, outcomes, handoffs, commits, and workflow health.

Dependencies:

- TASK-017 must be `COMPLETED`.
- TASK-019 must be `COMPLETED`.

Scope:

- Add `orc web` using the existing global `--state-file` option. It binds only
  to `127.0.0.1` by default, listens on an optional explicitly supplied port
  (default `8765`), and remains running until the operator interrupts it.
  There is no directory or task argument; the page reads every task in the
  selected state file.
- Update `README.md`, `design_docs/agent_workflow.md`, and the CLI help in
  `orc` with the `web` command, endpoint, pagination, redaction, content-type,
  bound, and read-only operator contracts.
- Implement the server with bounded standard-library HTTP handling and the
  existing state-file lock. Every request takes a consistent read snapshot,
  never mutates or migrates state, never launches a child, and returns a
  deterministic error rather than partial data for an invalid state file.
  Concurrent writers must not produce a mixed-task snapshot.
- Serve `/` as a self-contained UTF-8 HTML page with no external scripts,
  fonts, images, or outbound network requests. Its only script is inline and
  its only network access is same-origin `fetch` to Orc's read-only
  `/api/tasks?page=N` endpoint. Escape all state-derived text before HTML
  insertion and send this exact restrictive policy:
  `default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src 'none'; font-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'`. Refresh data
  through the read-only JSON API without requiring a page restart.
- Serve `GET /api/tasks?page=N` with a JSON object containing `tasks`,
  `generated_at`, `schema_version`, `aggregates`, `page`, `page_size`,
  `page_count`, and `total_tasks`, in that order. `page` is a one-based
  integer with a default of 1, `page_size` is the fixed integer 64,
  `page_count` is `max(1, ceil(total_tasks / 64))`, and `total_tasks` is the
  integer count across the complete state snapshot. `tasks` contains only
  that page's task summaries in lexicographic `task_id` order; every retained
  task is therefore reachable through pagination. `generated_at` is an
  RFC3339 UTC timestamp with `Z` and second precision, and
  `schema_version` is the integer `3`. `aggregates` has exactly
  `task_counts_by_status` (integer counts for `active`, `paused`, `blocked`,
  `stopped`, and `completed`), `task_counts_by_backend` (integer counts for
  `codex` and `claude`), `completion_rate`, `blocked_rate`, and
  `stopped_rate` (JSON numbers from 0.0 through 1.0, using 0.0 when there
  are no tasks), `total_finished_wall_seconds` and
  `average_finished_wall_seconds` (JSON numbers, zero when there are no
  finished tasks), `agent_wall_seconds` (integer `implementer` and
  `reviewer` values), `unattributed_wall_seconds` (an integer),
  `rounds_per_task` (objects with exactly `task_id` and `round`, sorted by
  `task_id`, containing only the tasks on the requested page), and
  `most_recent_task_activity` (an RFC3339 UTC timestamp or null). All other
  aggregate values are computed across the complete state snapshot. The root
  combines the page-local `rounds_per_task` lists while it loads pages. Each
  task summary has exactly `task_id`, `status`, `phase`,
  `backend`, `backend_version`, `target_directory`, `round`, `max_rounds`,
  `task_started_at`, `task_finished_at`, `wall_seconds`,
  `agent_wall_seconds`, `unattributed_wall_seconds`, `last_commit`, and
  `last_handoff_time`. `GET /api/tasks/TASK-ID` returns an object with the
  summary fields first, followed by exactly `timing_generations`, `handoffs`,
  `git_evidence`, `audit_events`, `generated_at`, and `schema_version`.
  `timing_generations` contains the exact bounded generation records from
  TASK-017 in chronological order. `handoffs` is the chronological list of
  accepted handoffs, each using exactly the redacted `last_handoff` object
  defined by TASK-019; it contains no canonical frame, launch token, prompt,
  backend command, raw payload, or transcript. `git_evidence` is the exact
  TASK-018 object or null. `audit_events` is the retained chronological list
  of TASK-017 events with its exact event fields and redaction rules.
  `generated_at` and `schema_version` have the same types and values as the
  collection response. A page outside `1..page_count` returns HTTP 404 with
  a bounded JSON diagnostic. Missing tasks return 404; invalid state returns
  500 with a bounded JSON diagnostic; successful API responses are
  `application/json; charset=utf-8` with no ANSI formatting. The server
  computes aggregate values across all tasks, not just the requested page.
- Only schema-3 records are accepted by the web view. A schema-2 record is
  private pre-baseline data and returns the bounded HTTP 500 diagnostic
  `unsupported pre-baseline state schema`; the server does not migrate,
  project, write, or revise it. Other unsupported versions and malformed
  schema-3 records return the same bounded HTTP 500 error without mutation.
- Compute dashboard aggregates from the complete state snapshot: task counts
  by status and backend, completion/blocked/stopped rates, total and average
  wall time for finished tasks, total wall time per role, total unattributed
  time, rounds per task, and the most recent task activity. The denominator
  for each rate is `total_tasks`; completed, blocked, and stopped are the
  respective numerators, and every rate is 0.0 when there are no tasks.
  Finished tasks are those whose current status is `completed`, `blocked`,
  or `stopped`; `active` and `paused` tasks are not finished, and a resumed
  task contributes only its current status and timing. The finished-time
  average divides by the count of those finished tasks and is zero when that
  count is zero. `most_recent_task_activity` is the maximum valid non-null
  `activity.implementer.last_activity_at` or
  `activity.reviewer.last_activity_at` value when TASK-020 metadata is
  present; if no such value exists, it is the latest valid
  `last_handoff_time`, otherwise null. Show timing as wall-clock elapsed time
  at the persisted whole-second precision; label CPU time, token usage, and
  billing data as unavailable rather than estimating them.
- Display a task table, status/backend filters, summary cards, and a task
  detail timeline. Show role durations, round transitions, accepted and
  rejected handoffs, bounded diagnostics, commit/Git evidence, and verification
  results when available. Do not display prompts, launch tokens, backend
  command argv, raw backend payloads, or transcript text. Optional fields from
  later Git, status, or health tasks are displayed when present and otherwise
  shown as unavailable.
- Add HTTP, HTML, API-schema, state-lock, escaping, redaction, empty-state,
  invalid-state, missing-task, concurrent-writer, and read-only regression
  tests. Tests use an ephemeral localhost port, prove the server handles
  multiple requests, and prove file bytes, revisions, timestamps, and child
  process state are unchanged.
- Bound each web response while preserving access to every retained task.
  The fixed page size is 64; the complete selected state snapshot is
  validated under the state lock, and each page is serialized independently.
  If the UTF-8 JSON response would exceed 1,048,576 bytes for
  `/api/tasks?page=N` or 262,144 bytes for `/api/tasks/TASK-ID`, return HTTP
  413 with the JSON object
  `{"error":"web response exceeds configured bound"}` and no partial data.
  The root page is a bounded static self-contained HTML shell that follows
  the same-origin paginated API until all pages are loaded, then applies its
  filters; it
  displays the same bounded error instead of partial task data when a page
  limit is reached. `GET /` success responses use
  `text/html; charset=utf-8`; root errors use `text/plain; charset=utf-8`.
  API successes and all API 404, 413, and 500 errors use
  `application/json; charset=utf-8` and a bounded `error` string.

Acceptance criteria:

- A local browser can view all retained tasks and filter them without exposing
  sensitive agent or operator data.
- API responses have stable keys and types, bounded payloads, correct 404/500
  behavior, and timing values matching TASK-017's timing contract.
- Dashboard aggregates are correct for empty, active, completed, blocked,
  stopped, resumed, multi-round, and mixed-backend task fixtures.
- The server binds to localhost by default, does not make outbound requests,
  and exits cleanly on Ctrl-C without changing task state.
- README, CLI help, and workflow documentation describe the same web contract
  and pass the applicable documentation verification.
- Verification Profile A passes on Linux, with every command and result
  recorded in the handoff and review document.

## TASK-018 - Record stronger Git evidence at handoff

State: NEW

Goal:

- Let operators and agents distinguish committed work from uncommitted files,
  including the exact repository and branch state at every accepted handoff.

Dependencies:

- TASK-016 must be `COMPLETED`.
- TASK-017 must be `COMPLETED`.

Scope:

- Update the Linux handoff and Git-evidence code in `orc`, the canonical
  handoff/context documentation, and the audit-event integration defined by
  TASK-017.
- Add fake-Git, real temporary-repository, timeout, and non-repository tests
  in `tests/`.
- Replace the short-hash-only evidence with a bounded `git_evidence` object
  whose exact fields are: `is_git_repository` (boolean or the literal
  `unknown`), `head` (40 lowercase hex characters, null for an empty
  repository, or `unknown` on command failure), `branch` (the branch name,
  `detached`, `unborn`, null for non-Git, or `unknown` on command failure),
  `worktree_clean` (boolean or null), `changed_files` (a list of paths),
  `changed_files_truncated` (boolean), and `error` (a bounded string or
  null).
- Collect evidence in the target directory without a shell using the exact
  argv `git rev-parse --verify HEAD`, `git symbolic-ref --short -q HEAD`, and
  `git status --porcelain=v1 -z --untracked-files=all`, each with the existing
  five-second timeout. Changed paths are capped at 128 entries and 512 UTF-8
  bytes per path; a path longer than 512 bytes is omitted and sets the
  truncation flag rather than being split or truncated. NUL-delimited status
  records are decoded with UTF-8 replacement; rename/copy records add both old
  and new paths in record order, with duplicates removed.
- The result matrix is exact: a target proven non-Git by normally completed Git
  probes has `is_git_repository: false`, `head: "unknown"`, `branch: null`,
  `worktree_clean: null`, an empty path list, and `error: null`; an empty Git
  repository has `true`, null head, `branch: "unborn"`, and a Boolean clean
  result; a detached repository uses `branch: "detached"`. A missing Git
  executable, timeout, malformed output, or other probe failure sets
  `is_git_repository: "unknown"` and only the dependent fields to `unknown`
  or null, while recording the bounded error. A normally completed negative
  `rev-parse` probe paired with successful non-repository classification is
  the only basis for `false`; if any probe cannot start, times out, or returns
  malformed output, the value is `unknown` instead. No failure may claim a
  clean tree or fabricate a commit/path.
- Attach the snapshot to accepted canonical handoffs, `last_handoff`, and the
  audit event. Keep `last_commit` as its existing short-hash-or-`unknown`
  string for compatibility, populated from a valid `head`; do not replace it
  with the object. Preserve the
  existing UTC/local timestamp, task, role, round, thread, and commit data.
- A timeout, missing executable, malformed output, or other Git error records
  the error and unknown/null dependent fields without claiming a clean tree;
  it must not fabricate a commit or changed-file list. A symbolic-ref exit
  status of 1 after successful `rev-parse` means normal detached HEAD and
  yields `branch: "detached"`; any other symbolic-ref failure yields
  `branch: "unknown"` and an error.
- Never include arbitrary Git command output, environment values, or user
  prompts in agent context; only the bounded structured object is delivered.

Acceptance criteria:

- Real temporary repositories cover clean, dirty, staged, untracked,
  detached-HEAD, empty/no-commit, and non-Git directories.
- Tests cover timeout, missing Git, malformed status output, path truncation,
  full-hash validation, missing/timeout Git with
  `is_git_repository: "unknown"`, both roles, both backends, and
  accepted/rejected handoffs without false clean/commit claims.
- Existing consumers of `last_commit` remain compatible while new status and
  audit consumers receive the complete structured snapshot. Records produced
  before TASK-018 and records during a partial rollout may omit
  `git_evidence`; readers must project that absence to null and writers must
  add the object without making the old record unreadable. Removal of any
  deprecated short-hash-only path requires a later task after all writers and
  readers have moved.
- Verification Profile A passes on Linux, with every command and result
  recorded in the handoff and review document.

## TASK-019 - Add a read-only task-status command

State: NEW

Goal:

- Provide a deterministic CLI view of persisted task state and recent workflow
  evidence without opening the TUI or mutating the task.

Dependencies:

- TASK-017 must be `COMPLETED`.
- TASK-018 must be `COMPLETED`.
- TASK-020 must be `COMPLETED`.

Scope:

- Add `orc status TASK-ID` to the CLI and a `--json` output variant, using
  the existing global `--state-file` option and no directory argument.
- Update the README, CLI help, and workflow documentation with the command's
  stable output, redaction, and exit-code contract.
- Add CLI/state-lock tests in `tests/`.
- The default output is fixed UTF-8 lines in this exact order and with these
  labels: `task_id:`, `status:`, `phase:`, `round: N/M`, `deadline:`,
  `backend:`, `backend_version:`, `target_directory:`, `igor_state:`,
  `rufus_state:`, `last_activity:`, `last_handoff:`, `git_evidence:`,
  `accepted_events:`, `rejected_events:`, and `diagnostics:`. Absent scalar
  values are `unknown`; absent activity, handoff, or Git evidence is `none`.
  Structured values use compact sorted JSON on their single line. Event
  sections contain at most the 20 newest matching events in chronological
  order, or `[]` when none exist. `last_handoff` is either `null` or a
  redacted object with exactly `schema_version`, `time`, `local_time`,
  `task_id`, `role`, `round`, `generation`, `thread_id`, `target_directory`,
  `commit`, `git_evidence`, `status`, `summary`, `files_changed`,
  `verification`, `blockers`, `requested_action`, and `reason`; absent
  optional values are null or empty lists. It never includes `canonical`,
  `launch_token`, `message`, or raw backend payload text.
  `accepted_events` contains only the 20 newest audit events whose `event` is
  `handoff_accepted`; each item has exactly the safe audit fields
  `sequence`, `time`, `event`, `role`, `round`, `generation`,
  `status_before`, `status_after`, `phase_before`, `phase_after`,
  `stop_reason`, `commit`, and `detail`. `rejected_events` is the 20 newest
  chronological union of audit events with `event: handoff_rejected` and
  persisted rejection diagnostics. Every item has exactly
  `source`, `sequence`, `time`, `event`, `role`, `round`, `generation`,
  `status_before`, `status_after`, `phase_before`, `phase_after`,
  `stop_reason`, `commit`, `detail`, and `reason`; audit items use
  `source: audit` and diagnostics use `source: diagnostic`, with fields not
  present in the source set to null. All projections exclude prompts, launch
  tokens, backend command argv, raw payloads, and transcript text.
- `--json` emits one object with these exact keys in the same order:
  `task_id`, `status`, `phase`, `round`, `max_rounds`, `deadline`, `backend`,
  `backend_version`, `target_directory`, `igor_state`, `rufus_state`,
  `last_activity`, `last_handoff`, `git_evidence`, `accepted_events`,
  `rejected_events`, and `diagnostics`. It has no ANSI formatting and uses
  JSON null for absent values. It includes at most 20 newest audit/rejected
  events but never prompts, launch tokens, backend command argv, raw payloads,
  or transcript text.
- Exit 0 means the task was found and valid. Exit 1 means the task ID is
  absent. Exit 2 means the state file is corrupt, schema-invalid, or cannot
  be read. Exit 3 means the state lock cannot be acquired within five
  seconds. Diagnostics go to stderr and partial status output is not emitted.
- The command acquires the same state lock for a consistent read, never
  increments a revision, never writes the state file, never launches a child,
  and works for active, blocked, stopped, paused, and completed tasks.

Acceptance criteria:

- Golden tests assert the exact default and JSON field order/content,
  nested handoff/event projections, redaction, chronological event limits,
  and exit code for every supported task status.
- Tests cover missing task, missing/corrupt/invalid state, concurrent writer,
  lock timeout, pre-baseline schema rejection, and a target with Git
  evidence.
- Running `uv run --script orc status TASK-ID` never changes file bytes,
  revision, timestamps, or child process state.
- Verification Profile A passes on Linux, with every command and result
  recorded in the handoff and review document.

## TASK-020 - Show stalled-agent health

State: NEW

Goal:

- Show when an active child has stopped producing or receiving activity while
  leaving legitimate long-running agent work uninterrupted.

Dependencies:

- TASK-017 must be `COMPLETED`.

Scope:

- Update the Linux TUI status model, bounded state/audit activity metadata,
  and README/workflow documentation in `orc`.
- Add fake-clock, real-PTY, resize, input, handoff, and child-lifecycle tests
  in `tests/`.
- Use a fixed documented `STALL_THRESHOLD_SECONDS` of 120 seconds. Persist
  an `activity` object with exactly these per-role fields: `last_activity_at`
  (an RFC3339 UTC string with `Z` and second precision, or null initially) and
  `last_activity_kind` (one of `launch`, `pty_output`, `input`, `handoff`, or
  null initially). Use wall-clock UTC for persisted timestamps and a monotonic
  clock only for local debounce; compute age as
  `max(0, floor(now_utc - last_activity_at))` seconds.
- Process activity in event-loop order. Within each one-second debounce
  interval, the last processed activity wins its kind and timestamp. Persist
  the coalesced latest value at most once per second per role. If persistence
  fails, retain the pending in-memory value, retry on the next tick, and do
  not claim a persisted update that did not succeed. The fixed two-role
  structure cannot grow without bound.
- `activity` is an additive, optional compatibility field for this task.
  Readers must treat it as absent/null for every record produced before
  TASK-020, and writers must be able to add it without rewriting or rejecting
  the rest of the record. Tests must load a pre-TASK-020 record, a partially
  updated record, and a fully updated record. Any later removal of the
  compatibility projection requires a separate deprecation task.
- For the currently active role with a live child, display its normal role
  state plus an age in seconds. At 120 seconds without activity, display
  `stalled` with the elapsed age and warning color; reset to `active` on the
  next valid activity. Waiting, inactive, failed, not-started, and terminal
  roles do not display as stalled.
- Refresh the health display once per second. Health is observational only:
  it must not kill a child, change task status, shorten the deadline, launch a
  replacement, or block keyboard input. The status command from TASK-019
  receives the bounded last-activity fields when present.
- If the clock is invalid, activity metadata is malformed, or the child is no
  longer live, fall back to the existing role state, display no age, and emit
  one bounded `activity unavailable` diagnostic per invalid record revision.
  Track the reported revision in memory so the diagnostic is not repeated on
  every one-second refresh. Never claim `stalled` without a live active child
  and a valid timestamp.

Acceptance criteria:

- Tests prove active output/input resets health, 119 seconds remains active,
  120 seconds becomes stalled, and later activity clears the warning.
- Tests cover both roles, both backends, no-permission mode, terminal resize,
  handoff waiting, child failure, stopped/completed tasks, and an idle agent
  that remains alive beyond the threshold without termination.
- State writes remain bounded and locked during high-volume PTY output, and
  the audit trail is not flooded with per-byte activity.
- Verification Profile B passes on Linux, with every command and result
  recorded in the handoff and review document.
