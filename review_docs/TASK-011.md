# Review: TASK-011

## Findings

### R001

Status: ADDRESSED

Terminal transitions do not recompute the active-agent border from persisted
state. `launch_role()` sets `self.active_role` to the running role, but
`poll_state()` handles `completed`, `paused`, `blocked`, `stopped`, and
deadline transitions by calling only `refresh_status()`. That path updates
status text and widgets but does not call `update_layout()`, which is the code
that adds and removes the `active-pane` class. The highlighted border can
therefore remain on Igor or Rufus after the persisted state says neither role
is active, violating TASK-011's active-agent mapping. The terminal-state tests
assert mounted status text but do not assert that both pane borders are
inactive after each transition.

Evidence:

- `orc:1394-1401` assigns the running role and updates the layout at launch.
- `orc:1785-1796` derives the border from the persisted active role.
- `orc:1828-1839` returns from terminal and deadline paths after refreshing
  status only.

Resolution:

- Terminal and deadline paths now call `refresh_workflow_ui()`, which
  recomputes the border from persisted status and phase while mounted.
- A real Textual test covers paused, blocked, stopped, and completed
  transitions and asserts that both pane borders are inactive.

### R002

Status: ADDRESSED

Resume migration loses the configured Codex executable for a valid legacy
record that has a persisted `codex` backend and target directory but no
`backend_command`. `stored_backend_command()` falls back to `['codex']` for
Codex instead of `codex_command()`, and `resume()` then persists that fallback
as the record's command. A `CODEX_COMMAND` path is consequently ignored on
resume and the child may fail to launch. TASK-011 explicitly permits such
legacy records and keeps executable-path configuration separate from backend
selection.

Evidence:

- `orc:618-622` hard-codes `['codex']` when the stored Codex command is absent.
- `orc:2136-2138` uses that fallback during resume validation.
- `orc:2172-2177` writes the fallback back into migrated state.
- `tests/test_orc.py:1626-1658` covers migration without asserting
  `CODEX_COMMAND` is honored.

Resolution:

- Missing persisted Codex commands now resolve through `codex_command()`,
  honoring `CODEX_COMMAND` before migration writes the command back.
- Legacy migration coverage asserts the configured executable is persisted.

### R003

Status: ADDRESSED

The test diff removes required coverage rather than preserving the existing
behavioral checks. In `test_orc_app_launch_error_and_invalid_records`, the
fixture is changed to omit the backend, so launch exits at backend validation
and the prior assertion for the `fork_codex()` OSError path is replaced by a
`no valid backend` assertion. The real-PTY selector parametrization also has
identical branches for `--codex` and `CODEX_COMMAND`, so it no longer exercises
the environment-default launch path separately. The review rules classify
removed coverage or narrowed inputs in test changes as material unless
evidence shows harness-only nondeterminism; no such evidence is recorded.

Evidence:

- `git diff HEAD^ HEAD -- tests/test_orc.py` removes the
  `could not launch reviewer` assertion and changes the fixture to a record
  without `backend`.
- `tests/test_orc.py:922-983` contains identical `selector` branches.

Resolution:

- The launch-error fixture again includes a valid Codex backend and exercises
  the `fork_codex()` OSError diagnostic.
- The PTY branches now distinguish explicit `--codex` with an invalid
  environment from `ORC_BACKEND=codex` without a selector, and assert the
  selected backend for both paths.

### R004

Status: ADDRESSED

The implementation commit is based on planning commit `75d61a9`, whose
TASK-011 round-indicator refinement still records
`review_docs/TASK-011-ROUND-PLANNING.md R001` as open and has no
`PLANNING_APPROVED` final decision. The commit message for `b812e18` explicitly
preserves that open planning item. The workflow requires an independently
approved planning specification before implementation review can complete.

Evidence:

- `review_docs/TASK-011-ROUND-PLANNING.md` has no final-decision section and
  leaves R001 `OPEN`.
- `git show -s --format=%B 9d4c069` records the planning review as open.

Resolution:

- The operator confirmed the round-indicator plan is approved. The planning
  review now records `PLANNING_APPROVED` in
  `review_docs/TASK-011-ROUND-PLANNING.md`.

### R005

Status: ADDRESSED

The worktree contains an unstaged change to
`design_docs/implementation_plan.md` that adds a new right-rail scope and
acceptance requirement. That change is not part of the shared task commit
`9d4c069`, so the active plan and the reviewed commit are different snapshots.
The completion criteria require a clean worktree and exactly one task commit;
the operator must decide whether this is a separately approved planning
refinement or revert it before TASK-011 can be completed.

Evidence:

- `git status --short` reports `M design_docs/implementation_plan.md`.
- `git diff 9d4c069 -- design_docs/implementation_plan.md` adds the right-rail
  scope and acceptance text.

Resolution:

- The operator reverted the right-rail refinement before this continuation.
  The worktree is clean and the active plan matches the reviewed task
  snapshot.

## Verification

- `uv run pytest -q`: PASS (152 passed).
- `uv run --script orc --help`: PASS.
- `uv run --script orc begin --help`: PASS.
- `uv run --script orc resume --help`: PASS.
- `python -m py_compile orc tests/test_orc.py`: PASS.
- `git diff --no-ext-diff --check HEAD^ HEAD`: PASS.
- Commit-message body line-length check: PASS.
- `uv run mdformat --check README.md design_docs docs review_docs`: PASS.
- `git status --short --branch`: PASS (clean worktree).

## Final decision

Status: COMPLETED
