# Implementation Plan

This file is the task source of truth for planned project work.

Before starting a new change, add a `NEW` task under `Tasks`. The shared state
transitions, commit contract, handoff procedures, review-document format, and
verification workflow are defined in `design_docs/agent_workflow.md`; role
responsibilities are defined in `docs/roles.md`.

Compatibility is forward-only. The private pre-release `v0.0.1` is not a
compatibility baseline, so persisted data and behavior from before the first
public release need not be migrated, projected, or preserved. Igor must reject
unsupported pre-baseline state before mutation or launch. Every later task
that changes a public schema or behavior must identify the established public
baseline, preserve its declared compatibility contract, and specify any
explicit migration or rejection behavior.

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

## TASK-022 - Restore operator input routing

State: COMPLETED

Goal:

- Restore operator-directed pane UX so one selected Igor or Rufus pane controls
  input, scrolling, highlighting, and Ctrl-R resume targeting while automatic
  workflow transitions and persisted phase truth remain authoritative.

Dependencies:

- TASK-013 must be `COMPLETED`.

Scope:

- Update the POSIX/Linux Textual input-routing and pane-selection behavior in
  `orc`; workflow lifecycle decisions and persisted task state remain driven
  by the existing workflow phase.
- Add unit and real-PTY tests in `tests/` for both implementer and reviewer
  sessions, keyboard input, paste input, pane clicks, Tab selection, state
  polling, handoffs, child retirement, and in-place resume.
- Update `README.md` and `design_docs/agent_workflow.md` with the unified
  selected-pane UX, retained pane availability, role-specific Ctrl-R resume,
  and the distinction between process-local selection and persisted workflow
  state.
- Keep one unified selected role process-local and never persist it or include
  it in handoff context. The selected role is simultaneously the input target,
  scroll target, Ctrl-R target, and highlighted pane; its highlight is the sole
  visible selection indication. A pane is unavailable only before that role
  has ever launched. After launch, it remains selectable for scrolling,
  highlighting, and Ctrl-R after its child exits or is retired.
- Before a manual selection, selection follows the active workflow role,
  including each implementer-to-reviewer or reviewer-to-implementer handover.
  Tab circularly cycles available launched roles in implementer-then-reviewer
  order; an available-pane click selects that pane. Either action creates a
  manual override.
  The override lasts until the next successful role handover, when the next
  child has launched and registered; selection then follows the newly active
  role again. If the next child launch fails, retain the previous valid
  selection and highlight. Pointer movement never creates a second selection.
  Selection changes never alter task state, phase, role state, handoff history,
  deadlines, launches, or audit data.
- Route the explicitly listed pass-through text, control, navigation, Enter,
  and paste bytes to the selected live child. If the selected child is not
  live, route only that write transiently to the live workflow-active child,
  then to the first other live child in implementer/reviewer order; retain the
  selected role and its highlight. If no child is live, ignore pass-through
  input. A live selected child is never replaced by a state-derived
  destination. Before every input write, move the pane receiving that write to
  its newest output so the operator can see the input context; fallback routing
  moves the actual fallback destination pane, while the unified selection
  remains unchanged.
- Outside the Ctrl-R prompt, Orc owns `Ctrl-Q` (quit), `Ctrl-R` (open the
  eligible resume prompt or consume as a no-op), `Escape` (consume as a
  no-op), `Tab` (circularly select an available launched pane), Page Up, Page
  Down, Home, and End (consume and scroll the selected pane), and all mouse
  press, release, move, and click events (consume; an available-pane click
  changes selection without sending bytes). `Shift-Tab` passes the exact bytes
  `ESC [ Z`; `1` and `2` pass their literal bytes. Enter passes `\r`, Backspace
  passes `\x7f`, Delete passes `ESC [3~`, and Up, Down, Right, and Left pass
  `ESC [A`, `ESC [B`, `ESC [C`, and `ESC [D` respectively. Printable text
  passes its UTF-8 bytes. Ctrl-A through Ctrl-Z pass their standard ASCII C0
  bytes except Ctrl-Q and Ctrl-R, which are Orc-owned; Ctrl-\[ is Escape and is
  consumed as the Escape no-op. Other unmapped, non-character key events are
  consumed as no-ops. Paste outside the prompt passes its UTF-8 bytes.
- While the Ctrl-R prompt is open, Ctrl-Q still quits; Ctrl-R and Tab are
  consumed no-ops that cannot change the resume target; Escape cancels; Page
  Up, Page Down, Home, and End remain Orc-owned scrolling; mouse events are
  consumed without changing selection; and all other text, control,
  navigation, Enter, and paste input belongs to the prompt editor. Enter
  submits only a non-empty request, and no prompt input reaches either child.
  With no live child, child-directed pass-through bytes are dropped, while all
  Orc-owned selection, scrolling, quit, and prompt rules remain available.
- Ctrl-R is available for every valid resumable terminal outcome: paused,
  blocked/clarification, completed, and stopped for orchestrator exit, child
  failure, deadline, maximum rounds, or manual pause, with each outcome's
  inactive-role predicate satisfied. It targets the unified selected role; an
  unlaunched role cannot be selected. A non-empty request appends to preserved
  request, handoff, audit, and prior-context history, retires remaining
  children, preserves identity/configuration/limits, clears terminal and
  launch-session metadata, starts a fresh deadline and bounded cycle, sets
  status active and phase to the selected role, marks only that role active,
  and launches it. Round 1 denotes the new cycle and does not erase prior
  round history. The selected role receives the request and then follows the
  normal handoff lifecycle.
- `orchestrator_exit` Ctrl-R coverage uses valid state fixtures in TASK-022;
  TASK-015 remains responsible for producing those records during cleanup and
  is not a TASK-022 dependency.
- Do not reload persisted state as the prerequisite for every keystroke. State
  polling may refresh workflow status and child availability, but it must not
  overwrite the unified selection except at a role handover or cause input to
  disappear during a phase transition.

Acceptance criteria:

- In a live TUI with both child PTYs, the operator can select Igor or Rufus by
  Tab or pane click and verified bytes, including text, Enter, control keys,
  arrow and other explicitly listed navigation bytes, Shift-Tab, `1`, `2`, and
  paste, arrive only at the selected child. The one highlighted pane is
  simultaneously the input, scroll, and Ctrl-R target, and pointer movement
  does not change it.
- Real Linux PTY/subprocess tests cover implementer and reviewer routing,
  selection changes, pointer movement, state polling, role handovers, pane
  retention after child exit/retirement, child exit between selection and
  write, failed next-child launch, and the no-live-child case. They prove
  fallback routing is transient, preserves selection, and reaches the correct
  live child; a failed handover retains the previous valid highlight.
- Tests prove clicks, Tab, pointer movement, and ordinary input do not mutate
  the persisted task record, revision, handoff history, deadline, role
  lifecycle, or audit data; resume-prompt input remains Orc-owned and is not
  delivered to either child.
- Tests prove input moves a manually scrolled receiving pane to the bottom,
  including the transient fallback destination, without changing the unified
  selected role or its highlight.
- Tests cover the complete key/event matrix, including exact pass-through bytes
  for text, control keys, Enter, Backspace, Delete, arrows, Shift-Tab, `1`,
  `2`, and paste; Orc ownership for Ctrl-Q, Ctrl-R, Escape, Tab, scrolling,
  mouse events, and prompt-open input; unknown key no-ops; and no-live-child
  behavior.
- Real-PTY tests cover Ctrl-R for every resumable terminal outcome, including
  completion, max-round, deadline, manual-pause, orchestrator-exit,
  clarification, and valid child-failure records. They cover selecting Igor or
  Rufus, rejecting an unlaunched Rufus pane, preserved context/history and
  configuration, fresh deadlines and round budgets, round-1 new-cycle truth,
  role-specific launches, handoffs, prompt delivery to only the selected role,
  and valid orchestrator-exit fixtures without a TASK-015 dependency.
- Automatic implementer-to-reviewer handoffs, both Codex and Claude launch
  paths, and normal selected-role handoffs retain their lifecycle behavior;
  in-place resume launches exactly the selected role with the preserved
  context and then uses the normal lifecycle.
- README and workflow documentation state the exact selection, fallback,
  retained-pane, handover, reserved-key, no-live-child, Ctrl-R, preserved-
  history, and process-local-state contract consistently, including the fixed
  implementer-then-reviewer fallback order.
- Verification Profile B passes on Linux, with every command and result
  recorded in the handoff and review document. Profile A also passes, with
  the exact final task commit snapshot used for all evidence.

## TASK-023 - Restore app-level focus for operator input

State: COMPLETED

Goal:

- Ensure ordinary operator keystrokes reach TASK-022's selected live child in
  the running Textual UI, while the Ctrl-R resume editor receives input only
  during an explicitly opened resume prompt.

Dependencies:

- TASK-022 must be `COMPLETED`.

Scope:

- Update the POSIX/Linux Textual focus and event-routing behavior in `orc` so
  the hidden `#resume-prompt` input cannot capture keyboard focus while it is
  inactive or before the first child launch. Keep TASK-022's selected-role,
  fallback, scrolling, reserved-key, paste, and no-live-child contracts
  unchanged.
- Define the focus lifecycle for the existing resume editor: inactive at
  application startup and during normal pane operation; focused when a valid
  Ctrl-R prompt is opened; and no longer focusable, with app-level routing
  restored, after Escape cancellation or submission handling completes. An
  ineligible Ctrl-R remains an Orc-owned no-op and must not focus the editor.
- Preserve prompt ownership while it is open: prompt text, editing controls,
  Enter submission, and paste remain prompt-owned; Ctrl-Q, Ctrl-R, Tab,
  Escape, Page Up, Page Down, Home, End, and mouse events retain TASK-022's
  Orc-owned behavior; no prompt input may reach a child PTY.
- Add focused Textual integration coverage in `tests/test_orc.py` for startup
  focus, ordinary printable and control-key delivery to a selected live PTY,
  prompt focus and child isolation, Escape cancellation followed by restored
  child routing, successful submission followed by restored child routing,
  and ineligible Ctrl-R. Cover both implementer and reviewer selection where
  the existing harness supports it, and verify that focus changes do not
  mutate persisted workflow state.
- Update `README.md` and `design_docs/agent_workflow.md` to state that the
  inactive resume editor is not an input target and that app-level operator
  routing is restored whenever the prompt is closed.

Acceptance criteria:

- In a live Linux Textual session before Ctrl-R is opened, the resume editor
  is not focused or keyboard-focusable, and printable text, Enter, control
  keys, navigation bytes, and paste follow TASK-022's selected-live-child or
  fallback routing exactly. The first keystroke after startup is delivered;
  it is not lost to the hidden editor.
- Opening Ctrl-R for every eligible resumable outcome focuses the editor and
  keeps all prompt text and paste in the editor. No prompt character,
  control, navigation, Enter, or paste byte reaches either child PTY.
- Escape closes an open prompt without submitting, makes the editor inactive,
  and restores app-level routing to the unchanged selected role. The next
  ordinary keystroke reaches the selected live child.
- A valid non-empty submission closes or transitions out of the prompt,
  leaves the editor inactive, and restores app-level routing after the
  submission handler has completed. Resume state, selected-role behavior,
  and preserved request/history semantics remain those specified by TASK-022.
- A rejected non-empty submission that leaves the workflow resumable keeps the
  editor open and focused so the operator can correct the request. If the
  workflow becomes no longer resumable while the prompt is open, the editor
  closes and app-level routing is restored without writing the rejected text
  to a child.
- Ctrl-R when no valid resume is available is consumed without focusing the
  editor or writing to a child. Ctrl-R and Tab while the prompt is open remain
  consumed no-ops, and mouse movement or clicks while it is open cannot create
  a new focus or selection target.
- Regression tests exercise real Textual event dispatch plus Linux PTY byte
  capture for both the normal selected-child path and the transient fallback
  path where applicable. They prove focus transitions do not alter persisted
  task status, phase, revision, role lifecycle, deadline, handoff history, or
  audit data except for the explicitly submitted resume request.
- Existing TASK-022 unit, real-PTY, Codex, and Claude lifecycle behavior
  remains passing. Verification Profile B passes on Linux, and Profile A
  passes against the exact final task snapshot, with every command and result
  recorded in the handoff and review document.

## TASK-015 - Make process and signal cleanup reliable

State: COMPLETED

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
- Update the normative state and workflow protocol in
  `design_docs/agent_workflow.md` so its schema, audit, timing, and
  compatibility rules match the implementation.
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
  from version 2 to version 3. Because `v0.0.1` is private pre-release,
  version-2 records are not part of the compatibility baseline: version-2
  and all other unsupported records are rejected before mutation with the
  bounded diagnostic `unsupported pre-baseline state schema`, and are never
  migrated, repaired, or launched. New schema-3 records add these fields and
  initialize `timing` with the current valid task start, a null
  `task_finished_at`, zero wall and role totals, zero unattributed time, and
  an empty generation list.
- Persist a bounded `timing` object for analytics consumers. Its exact fields
  are `task_started_at` (the immutable first-begin UTC timestamp),
  `task_finished_at` (the UTC timestamp of the current terminal transition or
  null while active), `wall_seconds` (the non-negative total from task start
  to finish, or from task start to the current UTC time while active),
  `agent_wall_seconds` (an object with exactly `implementer` and `reviewer`
  non-negative integer totals), `unattributed_wall_seconds` (a non-negative
  integer for task wall time not assigned to an agent generation), and
  `generations` (at most 256 records). Records are chronological by
  successful `launch_spawned`. When appending at the cap, evict the oldest
  record whose `ended_at` is non-null; open generations are never evicted.
  If all 256 retained records are open, reject the new launch before child
  spawn with the bounded diagnostic `timing generation retention full`, leave
  the state, revision, and history unchanged, and do not add a dropped
  counter. Each generation record has exactly
  `role`, `round`, `generation`, `launched_at`, `spawned_at`, `ended_at`,
  `end_event`, and `wall_seconds`; timestamps use the audit UTC format,
  `spawned_at`/`ended_at` may be null, `end_event` is null or one of
  `handoff_accepted`, `child_exit`, and `cleanup`, and `wall_seconds` is a
  non-negative integer or null while the generation is open. Retain the
  aggregate totals when old generation records are evicted.
- Define timing boundaries exactly: a generation starts at its successful
  `launch_spawned` event, ends at the first accepted handoff or its terminal
  `child_exit`/`cleanup`, and is counted once even if later retirement emits
  another child event. A task starts at its first `begin`; accepted resume
  starts a new active cycle without changing `task_started_at`, and clears
  `task_finished_at` until the next terminal transition. `wall_seconds` is
  the clamped non-negative whole-second difference between the relevant UTC
  timestamps; a backward wall-clock adjustment records a bounded diagnostic
  and contributes zero rather than a negative duration. At a terminal
  transition, `unattributed_wall_seconds` is
  `max(0, wall_seconds - implementer_seconds - reviewer_seconds)` and
  represents Orc/operator waiting or other time outside an open generation.
  CPU time, token usage, and model billing time are not inferred from these
  wall-clock values and are reported as unavailable unless a later task adds
  resource telemetry.
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
- Timing tests assert task wall time, per-role and per-generation elapsed wall
  time, handoff-versus-child-exit closure, aggregate preservation after
  generation eviction, resume cycles, unattributed time, and backward-clock
  handling. They prove a generation is never counted twice.
- Concurrent writers using the real state lock preserve monotonic sequence
  numbers, valid JSON, task revisions, and all non-evicted events.
- The 256-event cap and dropped counter are tested, including a full history
  during an active generation and redaction of every sensitive field.
- Loading a state file with malformed, oversized, out-of-order, or unknown
  audit data is rejected before mutation. `audit_next_sequence` must be
  greater than every retained sequence, retained sequences must be strictly
  increasing; `audit_dropped_count` must be an integer from 0 through
  1,000,000; and `last_terminal_event_key` must be null or a valid canonical
  JSON tuple string of at most 512 UTF-8 bytes. New schema-3 state starts
  with `audit_events: []`, `audit_next_sequence: 1`,
  `audit_dropped_count: 0`, `last_terminal_event_key: null`, and an explicit
  schema revision. Pre-baseline schema-2 records are rejected before
  mutation; migration is not required.
- Verification Profile A passes on Linux, with every command and result
  recorded in the handoff and review document.

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
