# Review: TASK-016

## Findings

### R001

Status: ADDRESSED

The new Ctrl-R regression now exercises the re-entrant retirement path that the
amended implementation claims to fix. The fixture constructs the app with two
inactive, retired sessions backed by real file descriptors and drives the
submission through real Textual `Input.Submitted` dispatch.

Evidence:

- `tests/test_task016.py:597-606` seeds inactive retired implementer and
  reviewer sessions with real descriptors.
- `tests/test_task016.py:607-614` drives Ctrl-R and the follow-up submission
  through `app.run_test` and Textual pilot events.
- `tests/test_task016.py:623-630` verifies both descriptors are closed, both
  old sessions are removed, and the restarted Rufus session is the sole active
  session.
- The parameterization at `tests/test_task016.py:516-522` covers both
  completed and stopped terminal records.

Resolution:

- The regression now covers both terminal fixtures, closes and removes the
  prior sessions during submission, and verifies successful Rufus restart.

## Verification

- `uv sync --locked`: PASS.
- `uv run pytest -q tests/test_task016.py -k textual_schema_v2_ctrl_r_restarts_selected_rufus_without_reentrancy_crash`: PASS (2 tests).
- `uv run pytest -q --cov=orc --cov-branch --cov-report=term-missing --cov-report=xml:coverage.xml --cov-fail-under=90`: PASS (332 tests,
  90.36% total coverage).
- `uv run pytest -q -m integration tests`: PASS (53 tests).
- `uv run ruff check .`: PASS.
- `uv run ruff format --check .`: PASS.
- `uv run mypy orc`: PASS.
- `uv run python -c "from pathlib import Path; compile(Path('orc').read_text(), 'orc', 'exec')"`: PASS.
- `uv run python -m compileall -q tests`: PASS.
- `uv run --script orc --help`: PASS.
- `uv run mdformat --check README.md design_docs docs review_docs`: PASS.
- `git diff --no-ext-diff --check HEAD^ HEAD`: PASS.
- `git show -s --format=%B HEAD | awk 'length($0)>60 {exit 1}'`: PASS.

## Final decision

Status: COMPLETED

R001 is addressed. TASK-016 is approved for completion.
