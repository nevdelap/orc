# Review: TASK-010

## Findings

### R001

Status: ADDRESSED

The mount-time lifecycle can still terminate or launch a role for a persisted
`paused` task. `on_mount` unconditionally schedules `launch_role(initial_role)`
after mounting (`orc:957-960`), but `launch_role` only treats `blocked`,
`stopped`, and `completed` as terminal (`orc:1187-1188`). It does not guard
`paused`. A paused record therefore bypasses the keep-alive path in
`poll_state`; depending on its saved request/session fields, the mount-time
call can launch a child or reach `fatal_error`, which calls `exit()`.

This violates TASK-010's requirement that paused tasks remain mounted for
inspection and that no role be launched after termination. The new tests cover
`poll_state()` on paused records, but do not exercise the real mount-time
callback against a persisted paused record.

Resolution:

- `launch_role` now returns before target/backend validation for all terminal
  statuses, including `paused`.
- A real Textual lifecycle test persists a paused record, verifies the app
  remains mounted, checks the paused status bar, and fails if a child launch is
  attempted.

Evidence:

- `orc:1180-1181` guards `paused`, `blocked`, `stopped`, and `completed`.
- `tests/test_orc.py:2684-2719` covers the persisted paused mount path.
- `uv run pytest -q` passes with 137 tests.

### R002

Status: ADDRESSED

The task commit message violates the shared commit contract's mandatory
60-column limit for body lines. The reviewer-pending item is 70 columns:

`- [open] review_docs/TASK-010.md R001 - Independent review is pending.`

The commit contract requires every body line, including `Implemented:` and
`Reviewed:` list items, to be at or below 60 columns. This prevents the task
from meeting the required clean commit handoff even though the product tests
pass.

Resolution:

- The reviewer-owned `Reviewed:` section was amended with a wrapped finding
  item while preserving the implementer's `Implemented:` section.

Evidence:

- The amended commit-message audit reports no body line above 60 columns.
- `design_docs/agent_workflow.md` requires body lines at or below 60 columns.

### R003

Status: ADDRESSED

Terminal metadata is not protected from a late child exit. `poll_children`
unconditionally writes `child_failure` and calls `set_stop_reason` when a
Codex child exits nonzero (`orc:1778-1791`), without checking whether the
loaded record is already `paused`, `blocked`, `stopped`, or `completed`.
The analogous Claude path in `handle_claude_exit` has the same issue
(`orc:1458-1470`). Because TASK-010 keeps the UI alive, an active child can
outlive a deadline or other terminal transition and a later poll can rewrite
the original terminal reason and diagnostics.

This violates the acceptance requirement that terminal polling be idempotent
and not mutate terminal metadata, and it can change a persisted `deadline` or
`completion` into `child_failure` after the user has reached the terminal UI.

Resolution:

- The shared `TERMINAL_TASK_STATUSES` set now guards launch and child-exit
  handling for `paused`, `blocked`, `stopped`, and `completed` records.
- Codex late nonzero exits are ignored for terminal records, and Claude's
  exit handler returns before recording diagnostics for those records.
- Parametrized tests cover late nonzero exits for both backends and all
  terminal status families exercised by the workflow.

Evidence:

- `orc:118`, `orc:1460`, and `orc:1784-1785` apply the terminal guards.
- `tests/test_orc.py:2878-2938` covers both backends and repeated polling.
- `uv run pytest -q` passes with 145 tests.

## Verification

- `uv run pytest -q`: PASS (145 passed).
- `uv run ruff check orc tests/test_orc.py`: PASS.
- `python -m py_compile orc tests/test_orc.py`: PASS.
- `uv run --script orc --help`: PASS.
- `uv run mdformat --check README.md design_docs docs review_docs`: PASS.
- `git diff --check HEAD^ HEAD`: PASS.
- `git status --short --branch`: clean before review metadata.
- The full TASK-010 diff was compared with TASK-008's accepted keep-alive
  requirement; the changed polling and child-exit paths no longer invoke
  `exit()`, while `Ctrl-Q` and `on_unmount` cleanup remain unchanged.

## Final decision

Status: COMPLETED
