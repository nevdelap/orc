# Review: task-015

## Findings

### R001

Status: ADDRESSED

The PTY read-error path does not use the centralized cleanup operation or
persist the required stopped workflow state. `read_session()` catches
`OSError`, removes the reader, drains once, and returns; it never calls
`cleanup()`. If the master reports `EIO` or another PTY error while the child
is still alive, the child process group remains live, its PTY master remains
open, and the state can remain active instead of recording
`orchestrator_exit` with inactive roles. This violates TASK-015's explicit
criterion that a PTY read error take the same cleanup path as an injected
uncaught exception.

Evidence:

- `orc:3486-3498` returns after `close_master_reader()` and `drain_session()`;
  no cleanup or stopped-state transition is attempted.
- `design_docs/implementation_plan.md:325-326` requires a PTY read error and
  injected uncaught exception to take the same cleanup path.
- `tests/test_task015.py` has no test that injects a PTY read error with a
  live child and checks process-group termination and persisted state.

Resolution:

- `read_session()` now routes an owned PTY `OSError` through the centralized
  cleanup operation after its final drain.

Evidence:

- `orc:3491-3508` invokes `cleanup()` for the live registered session.
- `tests/test_task015.py:test_pty_read_error_uses_orchestrator_cleanup`
  verifies stopped state, diagnostic, PTY closure, and child reaping.

### R002

Status: ADDRESSED

The added tests do not satisfy the required real Linux lifecycle matrix and
one test has no assertion that its claimed cleanup occurred. The only test
with a real child process exercises Ctrl-Q cleanup. The signal test has no
child and calls `_handle_signal()` directly, so it does not prove SIGINT,
SIGHUP, or SIGTERM cleanup of a real process group. There is no PTY read-error
test, terminal-disconnect test, or real uncaught-exception cleanup test. In
`test_run_app_exception_uses_cleanup_before_reraising`, the `calls` list is
never asserted; the `finally` cleanup would make the test pass even if the
exception handler's cleanup call were removed.

Evidence:

- `tests/test_task015.py:57-108` is the sole real-child cleanup test and only
  covers the Ctrl-Q/manual-pause path.
- `tests/test_task015.py:116-151` invokes one signal handler with no child;
  SIGINT and SIGHUP are not exercised.
- `tests/test_task015.py:235-254` creates a fake app but never checks its
  recorded cleanup calls.
- `design_docs/implementation_plan.md:322-331` requires all four exits,
  PTY read errors, injected failures, timing, descriptors, and orphan-child
  evidence using real Linux subprocesses/PTYs.

Resolution:

- Added real subprocess/PTY coverage for PTY errors, SIGINT, SIGHUP, SIGTERM,
  uncaught exceptions, and terminal disconnects, with cleanup assertions.

Evidence:

- `tests/test_task015.py:144-185` covers PTY errors and all three real
  signal paths.
- `tests/test_task015.py:335-365` covers real uncaught and disconnect
  failures, including state, descriptor, and child-reaping assertions.

### R003

Status: ADDRESSED

The task commit message violates the shared commit contract's 60-column body
limit. The reviewer must preserve Igor's `Implemented:` section while
recording this finding, so the invalid implementer-owned lines cannot be
silently rewritten during review.

Resolution:

- Igor wrapped the implementation bullets while preserving the shared
  message sections and trailer.

Evidence:

- `git show -s --format=%B HEAD | awk 'length($0)>60 {exit 1}'`: PASS on
  the final reviewed snapshot.

### R004

Status: ADDRESSED

The PTY-error ownership check includes normally retired sessions. A late
selector callback for a child that completed a normal handoff can therefore
call `cleanup()` and persist `orchestrator_exit`, stopping the next active
workflow instead of treating retirement as ordinary cleanup. This conflicts
with the workflow contract that retiring a completed child must not become a
workflow failure.

Evidence:

- `orc:3498-3508` treats any object in `retired_sessions` as owned and calls
  the workflow-wide cleanup operation on its PTY error.
- `orc:3884-3917` deliberately places normally handed-off children in
  `retired_sessions` after removing their reader, so a queued selector
  callback can reach this branch after retirement.
- No added test exercises a PTY error from a retired session while another
  role is active.
- `design_docs/agent_workflow.md` requires normal retirement to remain
  ordinary workflow cleanup and not be persisted as `child_failure`.

Resolution:

- PTY errors trigger workflow cleanup only for the current non-retired
  session. A retired session's queued error now closes its master without
  stopping the replacement workflow.

Evidence:

- `orc:3498-3512` distinguishes the current live session from retired
  sessions and closes the retired master without calling `cleanup()`.
- `tests/test_task015.py:test_retired_pty_error_does_not_stop_replacement_workflow`
  proves the active reviewer state is retained and the retired descriptor is
  closed.

## Verification

- `uv sync --locked`: PASS.
- `uv run pytest -q --cov=orc --cov-branch --cov-report=term-missing --cov-report=xml:coverage.xml --cov-fail-under=90`: PASS, 290 passed,
  90.12% coverage.
- `uv run pytest -q -m integration tests`: PASS, 47 passed.
- `uv run ruff check .`: PASS.
- `uv run ruff format --check .`: PASS.
- `uv run mypy orc`: PASS.
- `uv run python -c "from pathlib import Path; compile(Path('orc').read_text(), 'orc', 'exec')"`: PASS.
- `uv run python -m compileall -q tests`: PASS.
- `uv run --script orc --help`: PASS.
- `uv run mdformat --check README.md design_docs docs review_docs`: PASS.
- `git diff --no-ext-diff --check HEAD^ HEAD`: PASS.
- `git show -s --format=%B HEAD | awk 'length($0)>60 {exit 1}'`: PASS.
- Worktree clean at the reviewed snapshot.

## Final decision

Status: COMPLETED

R001 through R004 are addressed. TASK-015 is approved for completion.
