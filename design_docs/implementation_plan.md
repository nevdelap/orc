# Implementation Plan

This file is the task source of truth for planned project work.

Before starting a new change, add a `NEW` task under `Tasks`. The shared state
transitions, commit contract, handoff procedures, review-document format, and
verification workflow are defined in `design_docs/agent_workflow.md`; role
responsibilities are defined in `docs/roles.md`.

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

## TASK-014 - Add symmetric backend capability preflight

State: COMPLETED

Goal:

- Reject an incompatible Codex or Claude executable before Orc creates or
  mutates task state or launches an agent, with a useful version and contract
  diagnostic for either backend.

Dependencies:

- TASK-013 must be `COMPLETED`.

Scope:

- Update `orc`'s Codex and Claude adapters and launch path for Linux.
- Add focused fake-executable tests in `tests/` for begin, CLI resume, and
  in-place resume preflight behavior for both backends.
- Update the user documentation and workflow protocol with the shared
  preflight guarantees and each backend's launch contract.
- Configured `CODEX_COMMAND` and `ORC_CLAUDE_COMMAND` values remain argv
  values and are never invoked through a shell.
- Each probe incrementally captures combined stdout/stderr with a hard
  `PREFLIGHT_OUTPUT_LIMIT_BYTES` of 65,536 bytes; exceeding it terminates the
  probe, records `preflight output exceeds 65536 bytes`, and makes the
  backend incompatible without retaining more output. The five-second
  timeout also applies while draining the bounded capture.
- Each preflight runs, with argv exactly `[executable, "--version"]` and
  `[executable, "--help"]`, using `SUBPROCESS_TIMEOUT_SECONDS` equal to five
  seconds. It requires exit status zero, decodes combined stdout/stderr as
  UTF-8 with replacement, and uses the first non-blank output line as the
  version. A version line over 200 UTF-8 bytes is incompatible, stores
  `backend_version: unknown`, and produces the deterministic diagnostic
  `backend version line exceeds 200 bytes`. Missing output is stored as
  `unknown` and is incompatible. Invalid UTF-8 is therefore normalized with
  U+FFFD and is not itself a failure. Non-zero, timeout, output-limit, or
  `OSError` results produce the deterministic diagnostic
  `backend <name> executable <argv0> failed <probe>: <bounded detail>`.
- Codex additionally runs `[executable, "resume", "--help"]` with the same
  timeout and requires combined help output to contain the literal tokens
  `resume`, either `-c` or `--config`, and either `SESSION_ID` or
  `[SESSION_ID]`; resume help must also contain either `PROMPT` or `[PROMPT]`.
  The generated `notify` value must decode to exactly a JSON list of strings
  containing `uv`, `run`, `--script`, Orc's absolute path, `--state-file`, the
  absolute state path, and `idle-hook`, in that order with no extra values.
  The final launch argv must preserve the existing resume form.
- Claude's one `--help` probe must contain the literal tokens `--print`,
  `--output-format`, `stream-json`, `--input-format`, `text`, and `--resume`.
  Its final launch argv must preserve print/stream/text input mode and the
  existing session resume form.
- Missing backend capabilities or malformed launch configuration must fail
  before task-state creation on `begin`, and before state mutation or child
  launch on either resume path. The error must identify the backend,
  executable, and failed contract or bounded command diagnostic.
- Agentbox's backend-specific no-permissions flag is added only after a
  successful preflight and remains present exactly once in the final argv.

Acceptance criteria:

- Compatible fake Codex and Claude executables pass their backend-specific
  probes, record their versions, and receive their existing launch argv and
  handoff configuration unchanged.
- Fakes missing each required capability, returning failure, timing out, or
  raising `OSError`, emitting an overlong version line, or exceeding the
  bounded help capture produce deterministic backend-specific diagnostics and
  leave the state file and child process set unchanged.
- Begin and both resume paths are covered for both backends, including an
  executable path with spaces, both command environment variables, and the
  Linux agentbox marker state.
- Tests prove no raw help or version transcript is injected into an agent
  prompt or persisted as task state.
- Verification Profile B passes on Linux, with every command and result
  recorded in the handoff and review document.

## TASK-015 - Make process and signal cleanup reliable

State: NEW

Goal:

- Ensure Orc leaves the terminal, child process groups, file descriptors, and
  persisted workflow in a recoverable state after normal quit or interruption.

Dependencies:

- TASK-013 must be `COMPLETED`.

Scope:

- Update the Linux/POSIX TUI lifecycle, child-session cleanup, and persisted
  workflow state in `orc`.
- Add real-PTY and subprocess tests in `tests/` for Ctrl-Q, `SIGINT`,
  `SIGHUP`, `SIGTERM`, terminal disconnect/error, unexpected Python failure,
  and repeated cleanup.
- Document the cleanup contract and operator recovery behavior in the README
  and workflow documentation.
- Centralize an idempotent best-effort cleanup path. It must stop every Orc
  child process group with `SIGTERM`, wait at most two seconds, use `SIGKILL`
  for survivors, reap children, remove event-loop readers, close every PTY
  master exactly once, and restore terminal settings before exit.
- A clean Ctrl-Q from an active task records `status: stopped`,
  `phase: stopped`, `stop_reason: manual_pause`, and
  `stop_diagnostic: "operator quit"` with inactive role states. A signal,
  terminal disconnect, or uncaught-exit cleanup records `status: stopped`,
  `phase: stopped`, `stop_reason: orchestrator_exit`, and a bounded
  `stop_diagnostic` naming the trigger, with inactive role states. Add
  `orchestrator_exit` to the normative stop-reason contract. Already
  `completed`, `blocked`, `paused`, or `stopped` tasks retain their terminal
  status, reason, diagnostic, and history.
- A stopped `orchestrator_exit` record is eligible for CLI and in-place resume
  exactly when both roles are inactive and the record validates. Resume
  requires a non-empty request, preserves identity/configuration/history,
  clears `stop_diagnostic` and terminal launch metadata, and starts Igor at
  round 1 with a fresh deadline. Active roles or malformed records are
  rejected without mutation.
- Cleanup must use the locked atomic state mutation path when possible and
  must leave enough valid state for the documented resume matrix. If state
  persistence itself fails, report the failure on stderr after still
  attempting child and terminal cleanup.
- A second signal during cleanup must not re-enter cleanup or skip reaping.
  `SIGKILL` remains an unavoidable hard-stop limitation and is documented.

Acceptance criteria:

- Ctrl-Q, `SIGINT`, `SIGHUP`, and `SIGTERM` each leave no live child process
  group, no open Orc PTY master, and a valid persisted record with the exact
  status/reason specified above.
- A PTY read error and an injected uncaught exception take the same cleanup
  path; cleanup is safe when called twice and when a child already exited.
- A resumed stopped task starts a fresh valid cycle, while a completed task is
  not changed by shutdown cleanup.
- Tests verify terminal restoration, process-group escalation timing,
  descriptor closure, state locking, and absence of orphan descendants using
  real Linux subprocesses/PTYs rather than mocks alone.
- Verification Profile B passes on Linux, with every command and result
  recorded in the handoff and review document.

## TASK-016 - Bound agent-controlled data

State: NEW

Goal:

- Prevent agent, backend, user-request, and diagnostic data from causing
  unbounded memory, state-file, or prompt growth while preserving useful
  handoff information.

Dependencies:

- TASK-013 must be `COMPLETED`.

Scope:

- Update the handoff parser, Claude stream reader, persisted state model, and
  recipient-context builder in `orc`.
- Add protocol, state, fake-backend, and PTY tests in `tests/`.
- Document the limits and overflow behavior in `docs/roles.md` and the
  workflow protocol.
- Keep these exact UTF-8 byte limits: a handoff frame is at most 16 KiB, a
  scalar is at most 4 KiB, a launch token is at most 256 bytes, a list item is
  at most 512 bytes, and each handoff list contains at most 32 items. A
  handoff exceeding any limit is rejected as a whole and cannot alter
  workflow state or enter a prompt.
- Limit each backend stream line/event to 64 KiB. Oversized or malformed
  backend data is discarded through the end of that event, produces one
  bounded rejected diagnostic, and is never forwarded as agent context.
  In-memory stream-event retention is capped at 256 events per child, with
  oldest events discarded and a non-negative `stream_dropped_count` integer
  that saturates at 1,000,000 rather than overflowing.
- Limit persisted `handoffs` to 128 entries per task, retaining the newest
  accepted handoff for each role and evicting the oldest other entries first.
  If no entry can be evicted, reject the new handoff with a bounded
  diagnostic and do not launch the next role.
- Operator user requests are retained in `user_requests` and
  `last_user_request`, because they are explicit workflow input. They are
  capped at 32 entries and 4 KiB per UTF-8 encoded request; an over-limit
  request is rejected before state mutation or launch. Generated Orc prompts
  are ephemeral and are never persisted; a generated prompt is capped at
  32 KiB before launch, with optional context reduced first and the exact user
  request never silently truncated.
- The 16 KiB handoff-frame limit counts the UTF-8 bytes of the complete
  `ORC_HANDOFF_V1: ` line and its JSON object. The delivered context limit
  counts the UTF-8 bytes of the complete delimiters, JSON, and newlines. An
  incoming frame over 16 KiB is rejected as a whole. If a valid canonical
  handoff needs context reduction, preserve status, summary, requested action,
  and blockers first; truncate optional file and verification lists from the
  end, then scalar detail if necessary, with an explicit marker. Never
  truncate a blocker into an empty list for `UNABLE_TO_PROCEED`; if the
  required fields alone do not fit, reject delivery and record a diagnostic.
- Keep rejected-event diagnostics at 64 entries and 4 KiB per diagnostic,
  using the existing truncation marker. The trusted built-in
  `IMPLEMENTER_PROMPT`, `REVIEWER_PROMPT`, continuation prompts, and
  handoff-format instructions may enter their intended agent prompt. In
  addition, only the bounded explicit operator request and canonical handoff
  context may enter an agent prompt. Raw Codex notifications, Claude stream
  events, backend help output, launch tokens, generated command transcripts,
  and other backend text are never persisted or injected.

Acceptance criteria:

- Boundary tests cover every byte/item/list/count limit, valid Unicode, exact
  limit values, one-byte overflow, duplicate JSON keys, malformed events, and
  oversized stream lines.
- Tests prove rejected data leaves state, role transitions, receipts, and
  recipient prompts unchanged, while accepted data retains the required
  summary and blocker information.
- Long-running fake sessions demonstrate bounded stream memory, handoff
  history, user-request history, diagnostics, and serialized state size.
- Both Codex idle-hook payloads and Claude stream events receive the same
  bounded treatment on Linux, including begin/resume and agentbox modes.
- Verification Profile B passes on Linux, with every command and result
  recorded in the handoff and review document.

## TASK-017 - Add a bounded workflow audit trail

State: NEW

Goal:

- Make workflow failures diagnosable from a bounded, atomic record of Orc's
  launches, protocol decisions, transitions, exits, and cleanup actions.

Dependencies:

- TASK-016 must be `COMPLETED`.

Scope:

- Update the versioned task-state schema and every state mutation path in
  `orc`, including idle hooks, child exits, resume, handoff transitions,
  deadline/max-round stops, and cleanup.
- Add state, concurrency, lifecycle, and failure-path tests in `tests/`.
- Document the audit event schema, retention, and redaction rules.
- Persist `audit_events` as a chronological rolling list of at most 256
  events per task, plus `audit_next_sequence` (an integer starting at 1),
  `audit_dropped_count` (a non-negative integer capped at 1,000,000), and
  `last_terminal_event_key` (a string or null, initially null). Under the
  state lock, assign
  the current sequence, increment `audit_next_sequence`, evict the oldest
  event when the cap is reached, increment the dropped count, and append the
  new event in one atomic write. Sequence numbers never repeat, even after
  every earlier event has been evicted. Saturate `audit_dropped_count` at
  1,000,000 rather than overflowing. TASK-017 advances the state schema
  from version 2 to version 3; version 2 records migrate by adding these
  fields, and all other versions are rejected before mutation.
- Every event has this exact schema: `sequence` is a positive integer;
  `time` is a UTC RFC3339 timestamp with `Z` and second precision; `event` is
  one of `launch_started`, `launch_spawned`, `handoff_accepted`,
  `handoff_rejected`, `state_transition`, `child_exit`, or `cleanup`; `role`
  is `implementer`, `reviewer`, or null; `round` is a positive integer;
  `generation` is a positive integer or null; `status_before` and
  `status_after` are valid task statuses or null; `phase_before` and
  `phase_after` are valid phases or null; `stop_reason` is a valid stop reason
  or null; `commit` is exactly null in TASK-017's initial schema-3 state and
  becomes the structured Git evidence object defined by TASK-018; and
  `detail` is a string whose UTF-8 encoding is at most 4 KiB and may be empty
  only for successful launch or transition events.
- Event applicability is exact: launch events require role and generation;
  accepted/rejected handoffs require role, generation, and detail;
  `state_transition` requires before/after status and phase; `child_exit`
  requires role, generation, and detail; and `cleanup` requires detail and
  may use a null role/generation. Invalid combinations are rejected.
- A terminal event is exactly a `state_transition`, `child_exit`, or `cleanup`
  event whose `status_after` is one of `paused`, `blocked`, `stopped`, or
  `completed`. Its identity is the tuple `(event, role, generation, status_after, phase_after, stop_reason)`. Persist
  `last_terminal_event_key` as the canonical compact JSON array of that tuple,
  UTF-8 limited to 512 bytes. An attempted terminal event with the same key is
  a no-op, while a different terminal event against an already terminal record
  is rejected without append. This suppression rule is independent of rolling
  event-list eviction, and an accepted resume resets the key to null.
- Append events through the same locked revisioned mutation used for task
  state. An event and the state transition it explains must be committed in
  one atomic state write. Concurrent idle-hook and UI mutations must not lose
  either event or transition.
- Redact prompts, launch tokens, backend command arguments, raw backend
  payloads, and session transcript text. The audit record may contain only
  role/generation/session-safe identifiers already approved by the protocol,
  bounded diagnostics, and Git evidence.
- Audit rejected handoffs and cleanup failures as well as successful events;
  terminal repeated events are recorded once and then treated as no-ops.

Acceptance criteria:

- Tests assert the exact event fields and event order for a complete
  implementer-to-reviewer round, a rejected/stale handoff, a child failure,
  deadline stop, resume, and shutdown cleanup.
- Concurrent writers using the real state lock preserve monotonic sequence
  numbers, valid JSON, task revisions, and all non-evicted events.
- The 256-event cap and dropped counter are tested, including a full history
  during an active generation and redaction of every sensitive field.
- Loading a state file with malformed, oversized, out-of-order, or unknown
  audit data is rejected before mutation. `audit_next_sequence` must be
  greater than every retained sequence, retained sequences must be strictly
  increasing; `audit_dropped_count` must be an integer from 0 through
  1,000,000; and `last_terminal_event_key` must be null or a valid canonical
  JSON tuple string of at most 512 UTF-8 bytes. Old valid state is migrated
  with `audit_events: []`, `audit_next_sequence: 1`,
  `audit_dropped_count: 0`, `last_terminal_event_key: null`, and an explicit
  schema revision.
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
  audit consumers receive the complete structured snapshot.
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
  lock timeout, legacy migration rejection, and a target with Git evidence.
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
