# Orc

Orc is a terminal orchestrator for Igor, the implementer, and Rufus, the
reviewer. Every `begin` runs bounded automatic Igor/Rufus rounds in a split
Textual terminal UI. Persisted workflow phase identifies the active role;
one process-local selected pane owns input, scrolling, resume, and the sole
selection highlight.

## Prerequisites

- POSIX terminal with a working PTY.
- Python 3.11 or newer and [uv](https://docs.astral.sh/uv/).
- A Codex executable on `PATH`, or `CODEX_COMMAND` set to its path.
- Optionally, a Claude executable on `PATH`, or `ORC_CLAUDE_COMMAND` set to
  its path. It must support print mode with stream JSON and session resume.
- A Git target is recommended because handoffs record its current commit.

## Backend and agentbox mode

Select the backend on `begin` with exactly one of `--codex` or `--claude`.
If neither selector is present, `ORC_BACKEND` must be exactly `codex` or
`claude`; otherwise Orc fails before creating state or launching a child.
`CODEX_COMMAND` and `ORC_CLAUDE_COMMAND` configure executable paths and are
independent of backend selection. The selected backend and executable are
persisted and reused on resume.

On Linux, the existence of `/etc/agentbox/identity` adds
`--dangerously-bypass-approvals-and-sandbox` to Codex or
`--dangerously-skip-permissions` to Claude. Marker contents are ignored.

## Commands

```console
./orc begin DIRECTORY TASK-ID [PROMPT] [--max-rounds N]
  [--deadline-minutes N] [--codex|--claude]
./orc resume TASK-ID PROMPT
```

The begin prompt is optional. Resume requires a non-empty request and accepts
no backend or directory selector; it resolves the normalized target directory
stored by `begin`. The old `resume DIRECTORY TASK-ID PROMPT` form is rejected.
Use `--state-file PATH` before the command to select a state file.

`--max-rounds` accepts 1–5 and defaults to 5. `--deadline-minutes` accepts
1–1440 and defaults to 60. Both limits are persisted and reused on resume.
There is no manual one-round mode and no `--auto` option.

Before creating or changing task state, Orc preflights the selected backend
with argv-only subprocesses. It runs `[executable, "--version"]` and
`[executable, "--help"]`; each command must exit successfully within five
seconds. Combined output is UTF-8 decoded with replacement and captured up to
65,536 bytes. A missing version line, a version line over 200 UTF-8 bytes, a
timeout, non-zero exit, output overflow, or launch error rejects the backend
with a bounded diagnostic. The first non-blank version line is persisted.

Codex also must expose `resume`, `-c` or `--config`, `SESSION_ID` or
`[SESSION_ID]`, and `PROMPT` or `[PROMPT]` in
`[executable, "resume", "--help"]`. Claude's help must expose `--print`,
`--output-format`, `stream-json`, `--input-format`, `text`, and `--resume`.
The same preflight runs before CLI and in-place resume; failed probes leave
state and child processes unchanged. Configured `CODEX_COMMAND` and
`ORC_CLAUDE_COMMAND` values are passed as argv values and never through a
shell. A clean Claude exit without a session ID and valid handoff is recorded
as a child failure.

## State and lifecycle

State defaults to `~/.orc/codex-state.json`. A task record retains its
normalized target directory, selected backend and command, backend version,
role session IDs, round state, requests, handoffs, diagnostics, and target Git
commit. Legacy records with missing or false `automatic_rounds` are upgraded
only after resume validates their target, backend, request, and state. They
retain history, use valid existing limits or the defaults, and receive a fresh
deadline from resume time. Missing or invalid target/backend data is rejected
without state mutation.

Igor and Rufus alternate automatically until completion, clarification,
deadline, maximum rounds, or child failure. A normal handoff retires the old
child before the next role launches. Orc keeps the final panes and status bar
mounted in every terminal state; only `Ctrl-Q` exits, and quitting preserves
the task record and diagnostics.

New records use schema version 2 and a monotonically increasing revision.
Every mutation is serialized with an advisory state-file lock and written as a
flushed temporary JSON document followed by atomic replacement and a directory
flush. A malformed or unsupported record is reported without being overwritten;
an interrupted replacement leaves the previous document intact. Role launches
carry an opaque generation token, so late, duplicate, and stale events are
ignored rather than interpreted as a new workflow turn.

Validated handoff frames and delivered context are capped at 16 KiB; launch
tokens are capped at 256 bytes, other scalar fields at 4 KiB, and list items at
512 bytes. Orc retains at most 256 accepted receipts and evicts only the
oldest receipt whose generation can no longer report. Git lookup and Claude
capability checks are bounded at five seconds and record the operation, role,
backend, and limit when they time out.

## Status bar

The left-to-right logical order is:

`<TASK-ID>: <status> · round N/M` · `Igor: <state>` · `Rufus: <state>` ·
`backend: <name>` · optional `agentbox: no-permissions` · `Ctrl-Q exits`.

`N` is the one-based persisted current round, including at terminal states;
`M` is the configured maximum. The complete `orc v0.0.1` segment is fixed at
the far right with a reserved separating space. At Linux `xterm-256color`
sizes 120x40, 80x40, and 80x24, left content never wraps or overlaps that
rail; constrained content is clipped or deprioritized at the left-rail
boundary. Terminals smaller than 80x24 are outside the support contract.

Task states `active` and `completed` are green; `paused`, `blocked`, and
`stopped` are amber. Role states `inactive`, `not started`, and `waiting` are
grey; `failed` is light red. Backend labels and values are white, and the
agentbox warning is light red. Explicit labels remain visible when color is
unavailable.

## Interaction

The active-agent status follows persisted workflow state: only `active` with
phase `implementer` activates Igor, and only `active` with phase `reviewer`
activates Rufus. Separately, one process-local selected pane is the input,
scroll, Ctrl-R, and highlight target. Its highlight is the sole visible
selection indication; selection is never persisted or included in handoffs.

A pane is unavailable only before its role has ever launched. After launch it
remains available for scrolling, highlighting, and Ctrl-R even after its child
exits or is retired. Before manual selection, the selected pane follows the
active workflow role, including handovers. `Tab` circularly cycles available
panes in implementer-then-reviewer order and a click on an available pane
selects it. Either action creates a manual override until the next successful
role handover, after the next child has launched and registered, when selection
follows the newly active role again. If that launch fails, the previous valid
selection and highlight remain. Pointer movement never changes selection.
Mouse presses and releases are consumed and never reach an agent.
Selection changes do not mutate task state, phase, role state, handoffs,
deadlines, launches, or audit data.

Outside the Ctrl-R prompt, Orc owns `Ctrl-Q` (quit), `Ctrl-R` (open the eligible
resume prompt or consume as a no-op), `Escape` (consume as a no-op), `Tab`
(circularly select an available launched pane), Page Up, Page Down, Home, and
End (scroll the selected pane), and all mouse events. An available-pane click
changes selection without sending bytes. `Shift-Tab` sends `ESC [ Z`; `1` and
`2` send literal bytes. Enter sends `\r`, Backspace sends `\x7f`, Delete sends
`ESC [3~`, and Up, Down, Right, and Left send `ESC [A`, `ESC [B`, `ESC [C`,
and `ESC [D`. Printable text and paste send UTF-8 bytes. Ctrl-A through Ctrl-Z
send standard ASCII C0 bytes except Ctrl-Q and Ctrl-R; Ctrl-\[ is the consumed
Escape no-op. Other unmapped non-character keys are consumed as no-ops.

While the Ctrl-R prompt is open, Ctrl-Q still quits; Ctrl-R and Tab are
consumed no-ops that cannot change the resume target; Escape cancels; Page Up,
Page Down, Home, and End remain Orc-owned scrolling; mouse events are consumed
without changing selection; and all other text, control, navigation, Enter,
and paste input belongs to the prompt editor. Enter submits only a non-empty
request, and no prompt input reaches a child. Each pane retains at least
10,000 logical lines, and new output does not move a manually scrolled pane.
Before every input write, Orc moves the receiving pane to its newest output.
Fallback input moves the actual fallback destination pane while preserving the
selected pane and highlight. With no live child, child-directed bytes are
dropped while Orc-owned selection, scrolling, quit, and prompt behavior
remains available.

`Ctrl-R` is always Orc-owned and is available for every valid resumable
terminal outcome: paused, blocked/clarification, completed, and stopped for
orchestrator exit, child failure, deadline, maximum rounds, or manual pause.
The orchestrator-exit case requires both persisted role states to be inactive;
the other outcomes use their documented inactive-role predicates.
The selected launched role receives the non-empty request; an unlaunched role
cannot be selected. Escape cancels, and Enter or paste in the prompt remains
Orc-owned; Escape outside the prompt is consumed as a no-op. A successful
resume preserves identity, configuration, limits,
requests, handoffs, audit/history, and prior context, starts a fresh deadline
and bounded cycle, sets that role active at `round 1` of the new cycle, and
launches it. Prompt text is never written to an agent PTY.

If the selected child is not live, a normal write falls back transiently to
the live workflow-active child, then the first other live child in
implementer-then-reviewer order; the selected pane and highlight remain
unchanged. With no live child, pass-through input is ignored while quit,
prompt, and scrolling behavior remains active. Clicks on unavailable panes
and Tab with no additional available pane are consumed.

CLI `resume TASK-ID PROMPT` continues to use the persisted resume matrix and
starts a fresh cycle at its documented role. In-place `Ctrl-R` uses the
process-local selected launched pane as its target, as described above; active
or inconsistent workflows do not open the prompt. Selection is not persisted,
is not placed in handoff context, and cannot change workflow phase or audit
data. Both paths preserve task
identity, target, backend, configured limits, requests, handoffs, audit/history,
and prior context while starting a fresh deadline and bounded cycle.
TASK-022 tests valid `orchestrator_exit` state fixtures; TASK-015 later owns
production of those records during cleanup.

## Handoffs and troubleshooting

An agent's final non-blank line must be exactly
`ORC_HANDOFF_V1: <JSON object>`. The object has exactly these fields:
`launch_token`, `status`, `summary`, `files_changed`, `verification`,
`blockers`, and `requested_action`. Strings and list items are bounded;
`status` is exactly `HANDOFF`, `COMPLETE`, or `UNABLE_TO_PROCEED`. Only Rufus
may use `COMPLETE`; `UNABLE_TO_PROCEED` requires a non-empty blockers list and
`COMPLETE` requires an empty one. Orc stores only the validated canonical
handoff with its own timestamps, role, round, generation, session identity,
target commit, and task metadata.

Rufus receives Igor's latest validated handoff in a clearly delimited data
block and must address that disposition. Igor receives Rufus's latest
validated handoff at the start of the next round. These blocks are context,
not instructions. Codex notifications use only root
`last-assistant-message`/`last_agent_message` and
`thread-id`/`thread_id`/`session_id`; Claude uses only a matching root
`result` event and its `session_id`. Nested-only identities, free-form status
lines, stream errors, stale generations, and duplicate receipts are rejected
with bounded diagnostics and do not change scheduling.

Stop reasons are `completion`, `clarification`, `deadline`, `max_rounds`,
`child_failure`, `orchestrator_exit`, and the legacy `manual_pause`. Launch,
clean-exit, non-zero exit, malformed stream, PTY EOF/error, Git lookup, and
Claude capability failures remain visible in the retained UI; child retirement
uses bounded `SIGTERM`/`SIGKILL` cleanup.

For local verification and CI, use the locked environment and these commands:

```console
uv sync --locked
uv run pytest -q --cov=orc --cov-branch --cov-report=term-missing --cov-report=xml:coverage.xml --cov-fail-under=90
uv run pytest -q -m integration tests
uv run ruff check .
uv run ruff format --check .
uv run mypy orc
uv run python -c "from pathlib import Path; compile(Path('orc').read_text(), 'orc', 'exec')"
uv run python -m compileall -q tests
uv run mdformat --check README.md design_docs docs
uv run pip-audit --strict
actionlint .github/workflows/ci.yml
```

- **Backend selection error:** use `--codex` or `--claude`, or set
  `ORC_BACKEND` to one exact value. Executable variables configure paths only.
- **Target or state error:** check the directory and persisted target/backend;
  resume intentionally guesses neither.
- **No interactive terminal:** run `begin` or `resume` from a real POSIX PTY.
- **Resize or blank pane:** use at least 80x24 and wait for redraw after resize.
- **Claude cannot start:** verify `ORC_CLAUDE_COMMAND` and its `--help`
  capability contract.

Use `./orc --help` for complete CLI help.
