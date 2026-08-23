# Orc

Orc is a terminal orchestrator for two agent roles: Igor, the implementer, and
Rufus, the reviewer. Codex is the default backend; Claude Code can be selected
for a task. Orc keeps both roles in a split Textual terminal UI, forwards
input to the selected role, and pauses after each implement/review round so the
work can be inspected or resumed.

## Prerequisites

- POSIX terminal with a working PTY.
- Python 3.11 or newer.
- [uv](https://docs.astral.sh/uv/) for the recommended launch method.
- The `codex` executable available on `PATH`, or `CODEX_COMMAND` set to its
  path.
- Claude Code is optional. To use it, the `claude` executable must be on
  `PATH`, or `ORC_CLAUDE_COMMAND` must name the executable. It must support
  print mode with stream JSON and session resume.
- A Git target project is recommended because handoffs record its current
  commit. A target does not need to be the directory containing Orc.

## Agentbox mode

On Linux, Orc detects the agentbox confinement marker at
`/etc/agentbox/identity`. When that file exists, every Codex begin and resume
launch receives `--dangerously-bypass-approvals-and-sandbox`, and every Claude
begin and resume launch receives `--dangerously-skip-permissions`; the marker
contents are ignored. When it is absent, Orc leaves each backend's normal
approval and permission behavior unchanged. This is an agentbox environment
signal, not a user task option.

Agentbox provides the confined Sysbox container as the external safety boundary
for this mode; see the [agentbox GitHub repository](https://github.com/nevdelap/agentbox)
for that confinement model. The marker-based behavior is Linux-only.

## Launch

From an executable checkout, run Orc directly through its uv shebang:

```console
./orc begin DIRECTORY TASK-ID [PROMPT]
```

The equivalent explicit form is useful when diagnosing the launcher:

```console
uv run --script orc begin DIRECTORY TASK-ID [PROMPT]
```

Select Claude Code explicitly for a new task:

```console
./orc begin DIRECTORY TASK-ID [PROMPT] --backend claude
```

Orc probes the selected Claude executable with `--help` before creating task
state. The help output must advertise `--print`, `--output-format stream-json`, `--input-format text`, and `--resume`. Claude is run in print
mode with newline-delimited JSON; its session ID and final response are stored
in the shared task state. Resume uses the stored backend and session:

```console
./orc resume DIRECTORY TASK-ID PROMPT
```

Passing `--backend` to `resume` is optional, but if supplied it must match the
backend recorded by `begin`. `ORC_CLAUDE_COMMAND` is read at begin and the
selected executable is retained in task state, so resume does not silently
switch backends. A clean Claude exit without a session ID and valid handoff is
recorded as a child failure.

For a managed checkout, install the locked environment first, then use either
form above:

```console
uv sync --locked
./orc begin DIRECTORY TASK-ID [PROMPT]
```

`DIRECTORY` must already exist and be a directory. Orc resolves it to an
absolute path before creating state or launching a child. For example:

```console
uv run --script orc begin /work/my-project TASK-003 "Implement the next task"
```

The target can be outside Orc's own repository. Igor and Rufus start with that
directory as their working directory; Orc's state file and UI remain owned by
the Orc process.

## State

Orc stores state in `~/.orc/codex-state.json` by default. Override it before
the command with `--state-file`:

```console
uv run --script orc --state-file /tmp/orc-state.json begin DIRECTORY TASK-ID [PROMPT]
```

The task record retains the normalized target directory, backend and command,
backend version, Codex thread IDs or Claude session IDs, round state, user
requests, idle events, handoff messages, and the short Git commit observed in
the target repository. Keep the state file outside the target project when
the target has its own source-control or backup policy.

## Workflow

`begin DIRECTORY TASK-ID [PROMPT]` validates the target, creates a new task,
and starts Igor. The prompt is optional; when omitted, Igor receives Orc's
built-in implementer instructions without an empty user-request section. When
Igor becomes idle, Orc starts Rufus in the same target. Rufus reviews the target
worktree and reports findings without implementing fixes. After the review
becomes idle, Orc pauses the round. Use `resume` to send Igor a follow-up or to
ask for another implementation round:

```console
uv run --script orc resume DIRECTORY TASK-ID PROMPT
```

The resume directory is mandatory and must resolve to exactly the directory
stored for that task. A conflicting, missing, invalid, or non-directory path is
rejected before the state record is changed. A resume request must be non-empty;
when a task is paused for clarification, that request is the clarification
passed to Igor and is recorded exactly once.

For bounded automatic cycles, opt in explicitly at begin:

```console
uv run --script orc begin DIRECTORY TASK-ID PROMPT --auto \
  --max-rounds 5 --deadline-minutes 60
```

`--auto` runs Igor and Rufus repeatedly until completion, a blocker, child
failure, the configured round limit, or the persisted deadline. The limit is
1–5 rounds and the deadline is 1–1440 minutes; both default to 5 and 60. The
settings are saved with the task and reused by `resume`. Without `--auto`, Orc
keeps the manual one-round pause after Rufus. The automatic mode never resumes
after a clarification pause.

The compact status bar shows the task and current task status, Igor and Rufus
states, the selected backend, Orc's version, and the pane-switch hint. Role
states are `not started`, `active`, `waiting`, `inactive`, and `failed`. A role
that has handed off is `waiting` until the next workflow transition, even if
its child process is still alive. A completed task leaves both roles `inactive`
and keeps the UI visible until `Ctrl-Q`.

When the agentbox marker is present and the selected launch actually includes
the backend's no-permission flag, the bar also shows `agentbox: no-permissions`. Orc retires a normally handed-off child before launching the
next role or round; that lifecycle is not a `child_failure`.

## Handoffs and stop states

Each idle handoff is persisted with its role, round, thread, target commit,
UTC/local times, and the handoff fields. An agent may stop only when it cannot
proceed without a human and must report the exact status
`UNABLE_TO_PROCEED` plus a concise reason. Orc stores the blocker role, reason,
task, round, thread, timestamp, commit, and phase, then launches no next role.

The persisted `stop_reason` distinguishes `completion`, `clarification`,
`deadline`, `max_rounds`, `child_failure`, and `manual_pause`. Duplicate idle
events and stale notifications are ignored, so they cannot create an extra
round or concurrent child.

## Interaction

Both role panes remain visible whenever the terminal supports the selected
layout. The active pane has a highlighted border and its role is shown in the
status line. Click either pane or press `Tab` to focus the next pane; focus
selection updates the border and status without sending the focus command to
the agent. `Ctrl-Q` exits the UI.

Ordinary keys, digits, control keys, arrows, Enter, Shift-Tab, paste, and
terminal resize signals are forwarded to the active Codex PTY. Shift-Tab uses
the terminal's reported control sequence when available. Orc keeps startup,
idle, and handoff messages in each pane, and displays the task name and Orc
version in the status bar. Exiting the UI does not delete task state; resume
the task later with the same target directory.

## Troubleshooting

- **Target directory error:** check that the path exists, is accessible, and
  is a directory. Use an absolute path when diagnosing symlink or mount issues.
- **Task already exists:** choose a new task ID or use `resume` with the stored
  target directory.
- **Unknown task:** use the same `--state-file` that was used for `begin`.
- **Resume directory mismatch:** inspect the task record and pass its
  normalized `target_directory`; Orc intentionally rejects a different path.
- **No interactive terminal:** run `begin` or `resume` from a real POSIX
  terminal rather than redirecting standard input or output. If `./orc` is
  not executable in a checkout, run `chmod +x orc` once or use the explicit
  `uv run --script orc` form.
- **Resize or blank pane:** Orc measures the rendered pane after layout and
  sends that width and height to the child PTY. If a pane looks blank after a
  terminal resize, wait for the redraw, then click the pane to make its focus
  and border state explicit. Extremely small terminals use a safe minimum; use
  at least 80x24 for normal operation.
- **Codex cannot start:** set `CODEX_COMMAND` or pass `--codex`, and verify the
  executable can run from the target directory.
- **Claude cannot start:** set `ORC_CLAUDE_COMMAND` to the Claude executable and
  run it with `--help`. Orc requires the print/stream/resume capability
  contract; an incompatible or unavailable command is rejected before task
  state changes.
- **Claude produced no handoff:** Claude print mode must emit stream JSON with
  a session ID and a final response containing the shared handoff `Status:`.
  A clean exit without those fields is intentionally a child failure.
- **Git commit is `unknown`:** the target may not be a Git worktree or its
  `HEAD` may be unavailable. Orchestration can still retain the handoff.

Use `./orc --help` for the complete CLI help. The help text also describes the Linux-only agentbox marker behavior. The hidden
`idle-hook` command is invoked by Codex notifications and is not normally run
by hand. Set `ORC_DISABLE_IDLE_HOOK=1` for general Orc testing when you
need to keep an agent session available without an automatic handoff.
