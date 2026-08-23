# Review: TASK-012

## Findings

### R001

Status: ADDRESSED

In-place resume leaks the PTY master of a child that has already exited.
`_retire_all_sessions()` removes an exited session from `self.sessions` at
`orc:1409-1415` without closing `session.master_fd` or moving it to
`retired_sessions`. The only remaining cleanup path, `on_unmount()`, iterates
those two collections at `orc:2273-2292`; after the removal it can no longer
close this descriptor. This path is reached after a child failure has been
persisted and the operator presses `Ctrl-R`, so repeated in-place recoveries
can leak one PTY descriptor per exited child.

Evidence:

- A direct harness with an exited session in `app.sessions` produced
  `closed_fds=[]`, `remaining_sessions={}`, and
  `retired_sessions=[]` after `_retire_all_sessions()`.
- `poll_children()` marks the session exited but does not close its master
  before the new resume path removes it (`orc:2097-2120`).
- The task requires submission to retire remaining child sessions safely and
  retain the existing PTY cleanup behavior.

Required resolution:

- Ensure an exited session's master fd is closed exactly once, or retained in
  a cleanup collection until the existing unmount cleanup closes it. Add a
  regression test for child-failure `Ctrl-R` recovery and fd/process cleanup.

Resolution:

- `_retire_all_sessions()` now closes exited session descriptors through the
  idempotent `close_session_fd()` helper before removing the session. Unmount
  and retired-child cleanup use the same helper, and the new regression test
  verifies one close and a `-1` descriptor marker.

Evidence:

- The direct harness now reports `closed_fds=[123]`, `master_fd=-1`, and an
  empty session collection after repeated cleanup calls.
- `tests/test_orc.py:781-810` covers the one-close behavior.

### R002

Status: ADDRESSED

The TASK-012 test diff does not provide the required behavioral coverage for
the new scroll/input contract. The added input test only checks that `Tab`
changes `scroll_target`; it does not exercise Page Up, Page Down, Home, or
End, nor assert that those keys are consumed without forwarding. The
scrollback test uses only one `SessionPane`, so it does not demonstrate
independent Igor/Rufus positions. The added resume integration test covers
only the completed state and does not cover cancellation, empty submission,
blocked/paused/stopped eligibility through the real prompt, or inconsistent
terminal combinations. The status-bar integration test checks only the
version widget's text and right edge, not left-content non-overlap at the
three required sizes.

Evidence:

- `tests/test_orc.py:464-475` creates and exercises only one pane.
- `tests/test_orc.py:650-682` has no Page Up/Page Down/Home/End events and
  the Tab assertion compares `writes[-1]` to the previous `2` write rather
  than proving that no write occurred.
- `tests/test_orc.py:892-946` covers only a completed-task submission.
- `tests/test_orc.py:949-983` asserts version text/region but does not
  inspect the rendered left segment boundaries.
- TASK-012 explicitly requires all of these cases in its test scope and
  acceptance criteria.

Required resolution:

- Add focused unit or real-TUI fixtures covering both panes, all scrolling
  keys and their forwarding behavior, retained output during PTY writes,
  all eligible/ineligible resume states and prompt outcomes, and the actual
  status segment boundary at 120x40, 80x40, and 80x24.

Resolution:

- The implementation adds independent two-pane scrollback coverage, explicit
  Page Up/Page Down/Home/End consumption and non-forwarding assertions,
  retained-output checks, cleanup and resume outcome fixtures, and rendered
  status boundary assertions at all three supported sizes.

Evidence:

- `tests/test_orc.py:464-479` covers independent pane histories and retained
  output.
- `tests/test_orc.py:654-700` covers Tab and all scroll-navigation keys.
- `tests/test_orc.py:781-963` covers cleanup, eligible resume states,
  cancellation, empty input, and inconsistent records.
- `tests/test_orc.py:987-1079` checks the real status widgets and rail
  boundary at 120x40, 80x40, and 80x24.

### R003

Status: ADDRESSED

The exact declared test gate does not pass on the final TASK-012 snapshot:
`uv run pytest -q` fails `test_begin_prompt_is_optional_and_empty_prompt_uses_built_in_instructions`
with `SystemExit: select a backend with --codex or --claude, or set ORC_BACKEND`. The test invokes `begin` without a selector or environment
configuration, while the completed TASK-011 backend contract requires one.
This leaves the repository's required full suite red, despite the prior review
record claiming 166 passed.

Required resolution:

- Update the test setup to provide the documented backend configuration, or
  resolve the product contract through the plan; do not weaken the backend
  validation merely to make the test pass. Rerun the exact clean-environment
  suite and retain all assertions.

Evidence:

- `uv run pytest -q`: FAIL, 1 failed and 165 passed.
- `ORC_BACKEND=codex uv run pytest -q`: PASS, 166 passed, confirming the
  failure is exposed by missing required test configuration.

Resolution:

- The optional-begin test now passes the documented `--codex` selector, so it
  does not depend on ambient backend configuration.

Evidence:

- `tests/test_orc.py:2624-2631` includes `--codex` in the test arguments.
- `env -u ORC_BACKEND -u CODEX_COMMAND -u ORC_CLAUDE_COMMAND uv run pytest -q`:
  PASS (166 passed).

### R004

Status: ADDRESSED

The working tree is not clean after the TASK-012 commit. It contains an
uncommitted `design_docs/implementation_plan.md` change adding TASK-013 and an
untracked `design_docs/review.md`. The completion criteria require a clean
worktree, and these future planning artifacts must not be silently folded into
or discarded from the TASK-012 implementation commit.

Required resolution:

- Preserve the TASK-013 planning work and `design_docs/review.md` in their own
  authorized change or otherwise reconcile them with the operator before
  TASK-012 completion; then rerun the clean-worktree check without changing
  the TASK-012 snapshot.

Evidence:

- `git status --short` reports ` M design_docs/implementation_plan.md` and
  `?? design_docs/review.md`.
- `git diff HEAD -- design_docs/implementation_plan.md` contains the new
  TASK-013 entry.

Resolution:

- The current TASK-012 review snapshot has no uncommitted TASK-013 planning
  artifacts or other worktree changes; TASK-012 is reviewed independently of
  future planning work.

Evidence:

- `git status --porcelain=v1` is empty.
- `git diff --stat HEAD` is empty.

## Re-review verification

- `env -u ORC_BACKEND -u CODEX_COMMAND -u ORC_CLAUDE_COMMAND uv run pytest -q`:
  PASS (166 passed).
- `uv run --script orc --help`: PASS.
- `uv run --script orc begin --help`: PASS.
- `uv run --script orc resume --help`: PASS.
- `uv run python -m py_compile orc tests/test_orc.py`: PASS.
- `uv run ruff check orc tests/test_orc.py`: PASS.
- `uv run mypy orc`: PASS.
- `uv run mdformat --check README.md design_docs docs review_docs`: PASS.
- `uv run pip-audit`: PASS.
- `git diff --no-ext-diff --check HEAD^ HEAD`: PASS.
- Clean-worktree verification: PASS.

## Verification

- `env -u ORC_BACKEND -u CODEX_COMMAND -u ORC_CLAUDE_COMMAND uv run pytest -q`:
  PASS (166 passed).
- `uv run --script orc --help`: PASS.
- `uv run --script orc begin --help`: PASS.
- `uv run --script orc resume --help`: PASS.
- `python -m py_compile orc tests/test_orc.py`: PASS.
- `uv run mdformat --check README.md design_docs docs review_docs`: PASS.
- `git diff --no-ext-diff --check HEAD^ HEAD`: PASS.
- Commit-message body line-length audit: PASS.
- Worktree was clean before this review record was added.

## Final decision

Status: COMPLETED

TASK COMPLETE
