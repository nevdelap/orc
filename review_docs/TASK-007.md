# Review: TASK-007

## Findings

### R001

Status: ADDRESSED

The implementation commit edits TASK-007's approved specification while
implementing it. Compared with the planning baseline, it changes the Goal
from explicitly renaming `orc.py`, removes the explicit rename requirement
from Scope, and replaces the acceptance criterion forbidding `orc.py`
references with the less precise phrase "the previous launcher filename."
The workflow requires the task to be fully scoped before implementation and
does not permit the implementer to narrow or rewrite its scope unilaterally.
Resolution: Igor restored the original TASK-007 Goal, Scope, and Acceptance
criteria from the planning baseline; only the required state transition and
the launcher-path update for the completed TASK-005 scope remain.

Evidence: `git diff HEAD^ HEAD -- design_docs/implementation_plan.md` shows
the TASK-007 specification unchanged from the planning commit.

### R002

Status: ADDRESSED

The shared commit message violates the Commit Contract's maximum 60-column
body-line length. The Implemented bullets beginning "Preserve configured",
"Update CI, static", and "Verify pytest" are 63, 63, and 67 characters long,
respectively. Amend the same commit with a wrapped Implemented section while
preserving its content and the review section.
Resolution: The Implemented section is now wrapped to the required 60-column
body-line limit, and Rufus preserved it unchanged while amending the review
section.

Evidence: `awk 'length($0)>60' <(git show -s --format=%B HEAD)` produces no
output.

### R003

Status: ADDRESSED

The new agentbox tests verify only the command list before execution: they
replace `OrcApp.fork_codex` with a lambda and use an internal list-valued
`app.args.codex` for the duplicate test. They do not execute a fake Codex
executable through the real PTY/process boundary for the marker-present and
marker-absent role/begin/resume cases, nor do they exercise the configured
`CODEX_COMMAND`/`--codex` CLI path with a spaced executable. TASK-007's Scope
explicitly requires construction and execution coverage and acceptance calls
for non-shell executable support. Add focused execution coverage without
weakening the existing assertions.
Resolution: Igor added a parametrized integration test that executes a real
fake Codex executable through `fork_codex` and a PTY. It covers both roles,
marker presence and absence, begin and resume, and both `--codex` and
`CODEX_COMMAND` selectors with an executable path containing spaces.

Evidence: `uv run pytest -q -m integration tests` passes 19 tests, and the
new fixture asserts the executed argv, cwd, exact marker-flag count, role,
and resume thread.

## Verification

- `./orc --help`: PASS.
- `uv run --script orc --help`: PASS.
- `uv run pytest -q --cov=orc --cov-report=term-missing --cov-fail-under=90`: PASS, 89 tests, 92.19% coverage.
- `uv run pytest -q -m integration tests`: PASS, 19 tests.
- `uv run ruff check .`: PASS.
- `uv run ruff format --check .`: PASS.
- `uv run mypy orc`: PASS.
- Extensionless launcher compile and test compile checks: PASS.
- `uv run mdformat --check README.md design_docs docs`: PASS.
- `uv run pip-audit --strict`: PASS.
- `git diff --no-ext-diff --check HEAD^ HEAD`: PASS.
- The worktree was clean before this review amendment.

## Final decision

Status: COMPLETED

All findings are addressed in the shared TASK-007 commit. The task is
approved.
