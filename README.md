# Orc

Orc is a terminal orchestrator for Igor, the implementer, and Rufus, the
reviewer. Every `begin` runs bounded automatic Igor/Rufus rounds in a split
Textual terminal UI. The workflow-active role receives input and has the
highlighted active-agent border.

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

For Claude, Orc probes the selected executable with `--help` before creating
state. The help must expose `--print`, `--output-format stream-json`,
`--input-format text`, and `--resume`. A clean Claude exit without a session
ID and valid handoff is recorded as a child failure.

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

The active-agent border follows the persisted mapping: only `active` with
phase `implementer` activates Igor, and only `active` with phase `reviewer`
activates Rufus. Paused, blocked, stopped, and completed tasks have no active
role. Mouse presses and releases are consumed and never change roles or reach
an agent. `Tab`, `Shift-Tab`, `1`, and `2` are forwarded to the workflow-active
agent as byte `0x09`, `ESC [ Z`, `1`, and `2`. Other ordinary input is also
forwarded only while a role is active; otherwise it is ignored. `Ctrl-Q` is
always the explicit exit action.

## Handoffs and troubleshooting

An idle handoff includes role, round, thread, target, UTC/local time, commit,
and handoff fields. A blocker must use the exact status
`UNABLE_TO_PROCEED` with a concise reason. Duplicate and stale events are
ignored. Stop reasons are `completion`, `clarification`, `deadline`,
`max_rounds`, `child_failure`, and the legacy `manual_pause`.

- **Backend selection error:** use `--codex` or `--claude`, or set
  `ORC_BACKEND` to one exact value. Executable variables configure paths only.
- **Target or state error:** check the directory and persisted target/backend;
  resume intentionally guesses neither.
- **No interactive terminal:** run `begin` or `resume` from a real POSIX PTY.
- **Resize or blank pane:** use at least 80x24 and wait for redraw after resize.
- **Claude cannot start:** verify `ORC_CLAUDE_COMMAND` and its `--help`
  capability contract.

Use `./orc --help` for complete CLI help.
