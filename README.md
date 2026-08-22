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

From this repository, run Orc with uv:

```console
uv run --script orc.py begin DIRECTORY TASK-ID PROMPT
```

For a managed checkout, install the locked environment first and run:

```console
uv sync --locked
uv run python orc.py begin DIRECTORY TASK-ID PROMPT
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

The active pane is shown with a highlighted border. Press `Tab` or `Shift-Tab`
to switch panes, `1` or `2` to select Igor or Rufus, and `Ctrl-Q` to exit the
UI. Ordinary keys, control keys, arrows, Enter, paste, and terminal resize
signals are forwarded to the active Codex PTY. Exiting the UI does not delete
task state; resume the task later with the same target directory.

## Troubleshooting

- **Target directory error:** check that the path exists, is accessible, and
  is a directory. Use an absolute path when diagnosing symlink or mount issues.
- **Task already exists:** choose a new task ID or use `resume` with the stored
  target directory.
- **Unknown task:** use the same `--state-file` that was used for `begin`.
- **Resume directory mismatch:** inspect the task record and pass its
  normalized `target_directory`; Orc intentionally rejects a different path.
- **No interactive terminal:** run `begin` or `resume` from a real POSIX
  terminal rather than redirecting standard input or output.
- **Codex cannot start:** set `CODEX_COMMAND` or pass `--codex`, and verify the
  executable can run from the target directory.
- **Git commit is `unknown`:** the target may not be a Git worktree or its
  `HEAD` may be unavailable. Orchestration can still retain the handoff.

Use `uv run --script orc.py --help` for the complete CLI help. The hidden
`idle-hook` command is invoked by Codex notifications and is not normally run
by hand.
