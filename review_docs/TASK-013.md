# Review: TASK-013

## Findings

### R001

Status: ADDRESSED

The required branch-aware coverage gate fails on the final task commit. The
exact command
`uv run pytest -q --cov=orc --cov-branch --cov-report=term-missing --cov-report=xml:coverage.xml --cov-fail-under=90` runs all 188 tests with 188
passed, but reports 76.99% total coverage and exits non-zero. The CI test job
runs the same failing command. TASK-013 requires at least 90% total
branch-aware coverage.

Evidence addressed: on the final task snapshot, the same exact command runs
223 tests with 223 passed and reports 90.06% total branch-aware coverage.

### R002

Status: ADDRESSED

Evidence addressed: `idle_hook` now wraps schema-v2 processing in
`mutate_task_state` (`orc:4099-4108`), and Claude error/session persistence
uses the same operation. The regression test at
`tests/test_task013.py:400-431` verifies a valid handoff advances revision
and a replay does not add a second handoff.

### R003

Status: ADDRESSED

Evidence addressed: `parse_handoff_message` bounds the incoming frame and
`_strict_idle_hook` validates the canonical delivered context before receipt
or transition (`orc:3939-3961`). The regression at
`tests/test_task013.py:433-470` confirms a frame-valid but undeliverable
handoff leaves phase and handoffs unchanged.

### R004

Status: ADDRESSED

Evidence addressed: `can_resume_in_place` validates the normalized target and
backend before applying the shared resume validator (`orc:2300-2316`), and
launches persist PID/live-child identity in both the launch record and history
(`orc:2800-2822`). Coverage at `tests/test_task013.py:1141-1156` checks target
and backend rejection; `tests/test_task013.py:1065-1100` checks PID
persistence.

### R005

Status: ADDRESSED

Required timeout diagnostics are incomplete. `current_commit` catches
`subprocess.TimeoutExpired` and returns `"unknown"` at `orc:1007-1022`, so a
Git lookup timeout is persisted in a handoff as an unknown commit with no
operation, role/backend, or elapsed-limit diagnostic. TASK-013 explicitly
requires Git lookup timeouts to remain truthful and report the affected
operation and limit.

Evidence addressed: `current_commit` now accepts diagnostics, strict idle
handoff processing persists the Git operation and five-second limit as a
structured child failure, and the timeout tests pass on the final task snapshot.

### R006

Status: ADDRESSED

Evidence addressed: `launch_role` checks receipt capacity before backend
launch (`orc:2589-2595`) and records a structured child failure. The direct
launch-boundary regression at `tests/test_task013.py:1159-1192` proves the
capacity stop and diagnostic; invalid-precondition coverage at
`tests/test_task013.py:1404-1437` now asserts rejection rather than masking
the failure handler.

### R007

Status: ADDRESSED

Evidence addressed: `_validate_state_document` now validates required
schema-v2 fields, status/phase, roles, launches, generations, child identity,
limits, stop reasons, timestamps, and bounded histories (`orc:146-419`). The
malformed-record matrix at `tests/test_task013.py:629-714` exercises these
rejections before state mutation.

### R008

Status: ADDRESSED

Evidence addressed: `receipt_capacity_blocked` resolves receipt generations
through launch history and conservatively retains reportable generations
(`orc:1049-1116`); `launch_role` enforces the capacity boundary before fork
(`orc:2589-2595`), while handoff processing evicts only proven-dead entries.
Coverage includes generation retention and launch-boundary stop behavior at
`tests/test_task013.py:717-763` and `tests/test_task013.py:1159-1192`.

## Verification

- `uv sync --locked` — passed.
- Full coverage command on the final task snapshot — 223 passed; 90.06%
  branch-aware
  coverage.
- `uv run pytest -q -m integration tests` — 27 passed, 196 deselected.
- `uv run ruff check .` — passed.
- `uv run ruff format --check .` — passed.
- `uv run mypy orc` — passed.
- Orc compile check — passed.
- Test compile check — passed.
- `uv run mdformat --check README.md design_docs docs` — passed.
- `uv run pip-audit --strict` — passed.
- `actionlint .github/workflows/ci.yml` — not run; executable is not
  installed in this workspace. The CI workflow installs actionlint in its
  security job.
- `git diff --check` — passed for the implementation snapshot.

## Final decision

Status: COMPLETED
