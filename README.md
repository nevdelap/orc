# Orc

Orc is a terminal orchestrator for two interactive Codex roles: Igor, the
implementer, and Rufus, the reviewer. It keeps both roles in a split Textual
terminal UI, forwards input to the selected role, and pauses after each
implement/review round so the work can be inspected or resumed.

## Prerequisites

- POSIX terminal with a working PTY.
- Python 3.11 or newer.
- [uv](https://docs.astral.sh/uv/) for the recommended launch method.
- The `codex` executable available on `PATH`, or `CODEX_COMMAND` set to its
  path.
- A Git target project is recommended because handoffs record its current
  commit. A target does not need to be the directory containing Orc.

## Launch

From an executable checkout, run Orc directly through its uv shebang:

```console
./orc.py begin DIRECTORY TASK-ID PROMPT
```

The equivalent explicit form is useful when diagnosing the launcher:

```console
uv run --script orc.py begin DIRECTORY TASK-ID PROMPT
```

For a managed checkout, install the locked environment first, then use either
form above:

```console
uv sync --locked
./orc.py begin DIRECTORY TASK-ID PROMPT
```

`DIRECTORY` must already exist and be a directory. Orc resolves it to an
absolute path before creating state or launching a child. For example:

```console
uv run --script orc.py begin /work/my-project TASK-003 "Implement the next task"
```

The target can be outside Orc's own repository. Igor and Rufus start with that
directory as their working directory; Orc's state file and UI remain owned by
the Orc process.

## State

Orc stores state in `~/.orc/codex-state.json` by default. Override it before
the command with `--state-file`:

```console
uv run --script orc.py --state-file /tmp/orc-state.json begin DIRECTORY TASK-ID PROMPT
```

The task record retains the normalized target directory, role thread IDs,
round state, user requests, idle events, handoff messages, and the short Git
commit observed in the target repository. Keep the state file outside the
target project when the target has its own source-control or backup policy.

## Workflow

`begin DIRECTORY TASK-ID PROMPT` validates the target, creates a new task, and
starts Igor. When Igor becomes idle, Orc starts Rufus in the same target. Rufus
reviews the target worktree and reports findings without implementing fixes.
After the review becomes idle, Orc pauses the round. Use `resume` to send Igor a
follow-up or to ask for another implementation round:

```console
uv run --script orc.py resume DIRECTORY TASK-ID PROMPT
```

The resume directory is mandatory and must resolve to exactly the directory
stored for that task. A conflicting, missing, invalid, or non-directory path is
rejected before the state record is changed.

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
  terminal rather than redirecting standard input or output. If `./orc.py` is
  not executable in a checkout, run `chmod +x orc.py` once or use the explicit
  `uv run --script orc.py` form.
- **Resize or blank pane:** Orc measures the rendered pane after layout and
  sends that width and height to the child PTY. If a pane looks blank after a
  terminal resize, wait for the redraw, then click the pane to make its focus
  and border state explicit. Extremely small terminals use a safe minimum; use
  at least 80x24 for normal operation.
- **Codex cannot start:** set `CODEX_COMMAND` or pass `--codex`, and verify the
  executable can run from the target directory.
- **Git commit is `unknown`:** the target may not be a Git worktree or its
  `HEAD` may be unavailable. Orchestration can still retain the handoff.

Use `./orc.py --help` for the complete CLI help. The hidden
`idle-hook` command is invoked by Codex notifications and is not normally run
by hand. Set `ORC_DISABLE_IDLE_HOOK=1` for general Orc testing when you
need to keep an agent session available without an automatic handoff.
