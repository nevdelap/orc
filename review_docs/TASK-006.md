# Review: TASK-006

## Findings

### R001

Status: ADDRESSED

The Claude session lookup can reuse the implementer's session as the
reviewer's first session. `handle_claude_exit` stores the latest session in
the task-level `claude_session_id`, while `claude_session_for_role` falls back
to that value when the requested role has no session. On the first reviewer
launch after a Claude implementer handoff, `launch_role` therefore treats the
reviewer as a resume. In manual mode there is no user request yet, so the
launch is rejected with `cannot resume reviewer: no user request recorded` and
Rufus never starts. In automatic mode it instead resumes Igor's Claude
conversation rather than starting the review role's initial turn.

Evidence: `uv run python` diagnostic using the repository's `app_stub` with
`claude_sessions: {"implementer": "igor-session"}` reported that exact fatal
error and captured no launch. The behavior is implemented by the fallback in
`claude_session_for_role` and the no-request guard in `launch_role`.

Resolution: `claude_session_for_role` now returns only the requested role's
saved session. A role with no saved session uses the initial command without
`--resume`, while resume uses that role's own saved session.

Evidence: `test_claude_sessions_are_role_specific` verifies that a reviewer
with only an implementer session launches without `--resume`, and
`test_claude_real_pty_resume_uses_role_session` verifies a real PTY resume
uses the saved reviewer session.

### R002

Status: ADDRESSED

`handle_claude_exit` does not interpret the child exit status before accepting
a parsed handoff. A Claude process that exits nonzero after emitting a session
ID and a handoff-shaped final response is passed to `idle_hook`, which can
record completion or advance the workflow. A failed backend process must be a
`child_failure` even if it emitted apparently valid final output.

Resolution: `handle_claude_exit` converts the wait status before parsing a
handoff and records `child_failure` for every nonzero exit.

Evidence: `test_claude_nonzero_exit_is_child_failure_even_with_handoff` passes
a nonzero wait status with valid stream data and verifies that no handoff is
recorded and `stop_reason` is `child_failure`.

### R003

Status: ADDRESSED

Resolution: Igor added focused Claude role, failure, unavailable-command,
resume, and agentbox PTY coverage, formatted `orc`, and wrapped the
Implemented commit bullets to the required width.

Evidence: `uv run pytest -q --cov=orc --cov-report=term-missing --cov-fail-under=90` passes 103 tests at 90.74%; `uv run ruff format --check .` passes; the commit-message width check reports no overlong lines; and the
new integration suite passes 25 tests, including both roles and marker states.

## Verification

- `uv run pytest -q`: PASS, 103 passed.
- `uv run pytest -q -m integration tests`: PASS, 25 passed.
- `uv run pytest -q --cov=orc --cov-report=term-missing --cov-fail-under=90`:
  PASS, 90.74% coverage.
- `uv run ruff check .`: PASS.
- `uv run ruff format --check .`: PASS.
- `uv run mypy orc`: PASS.
- `uv run python -m compileall -q tests`: PASS.
- `uv run mdformat --check README.md design_docs docs`: PASS.
- `uv run mdformat --check review_docs/TASK-006.md`: PASS.
- `uv run pip-audit --strict`: PASS.
- `uv run --script orc --help`: PASS.
- `git diff --no-ext-diff --check HEAD^ HEAD`: PASS.
- Commit-message width check: PASS.
- Worktree is clean after the review amendment.

## Final decision

Status: COMPLETED

All findings are addressed in the shared TASK-006 commit. The task is
approved.
