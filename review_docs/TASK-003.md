# Review: TASK-003

## Findings

### R001

Status: ADDRESSED

The task scope does not name the affected source, test, or fixture file
families. It describes behaviors such as CLI parsing, task-state persistence,
child launch, handoffs, and verification, but does not identify the files or
modules Igor is expected to change. The planning contract requires Scope to
list the expected files, modules, or documentation families, and the task must
be self-contained before implementation begins.

Evidence:

- `orc.py` currently contains the CLI, state, child-launch, idle-hook, and
  current-commit behavior, but it is not named in Scope.
- No test or fixture family is named even though Acceptance criteria require
  coverage of argument/state behavior, child CWD, resume persistence, and
  target-repository commit capture.

Resolution:

- TASK-003 now names `orc.py`, `README.md`, `tests/` and test fixtures, and
  the CI/configuration file family in Scope.

Evidence:

- `git diff --no-ext-diff HEAD^ HEAD -- design_docs/implementation_plan.md`
  contains explicit implementation and test/fixture families.

### R002

Status: ADDRESSED

The planning commit's `Implemented:` section says, "Create a complete
user-facing README for the tool," but this commit does not add or modify a
`README.md`. A planning commit may define that deliverable, but it must record
the planning change accurately and preserve the distinction between the
planning baseline and the later implementation commit.

Evidence:

- `git diff --no-ext-diff --name-status HEAD^ HEAD` contains only
  `design_docs/implementation_plan.md` and
  `review_docs/TASK-003.md`.
- `README.md` does not exist in the current repository tree.

Resolution:

- The shared commit message now describes defining TASK-003's target-directory
  behavior, README, tests, and CI; it no longer claims that `README.md` was
  created in the planning commit.

Evidence:

- `git show -s --format=%B HEAD` contains the revised `Implemented:` entry and
  preserves the required `Reviewed:` and model trailer sections.

### R003

Status: ADDRESSED

The refined plan adds a broad CI and quality scope without specifying the
external values needed to make the task self-contained. It requires
"supported" Python versions and Linux/macOS environments, plus comprehensive
quality, dependency, security, integration, and documentation checks, but it
does not name the supported versions, tools, check commands, or exact
configuration/dependency files. The planning contract prohibits relying on
the implementer to infer omitted platforms, variants, or external values.

Evidence:

- Scope names `.github/workflows/ci.yml` and vague
  "dependency/configuration files required by the checks," although neither
  file exists in the current tree.
- Acceptance criteria require CI on "supported Linux and macOS environments"
  and "the relevant" checks without defining those environments or checks.

Required resolution: specify the supported Python and OS versions, the exact
quality/test/integration/documentation/dependency/security commands, and the
precise configuration files allowed to change, or remove this newly introduced
CI scope if it is not part of TASK-003.

Resolution:

- TASK-003 now limits CI to Ubuntu 24.04 with Python 3.11, 3.12, 3.13, and
  3.14.
- Scope names the workflow, Dependabot, project, lock, and conditional ignore
  files.
- Acceptance criteria enumerate the exact sync, test, quality, type, compile,
  documentation, audit, and workflow-lint commands.

Evidence:

- `design_docs/implementation_plan.md` names the pinned platform and Python
  matrix, exact configuration files, and each required command.
- The plan remains a planning-only diff: no application source or tests are
  included in the shared commit.

### R004

Status: ADDRESSED

The idle-hook path can capture Orc's own repository commit when the task record
does not contain a valid target directory. `idle_hook()` only checks that the
task record is a dictionary, then passes `record.get("target_directory")` to
`current_commit()`; `current_commit()` treats `None` as the subprocess default
working directory. That default is Orc's process directory, so a stale
pre-TASK-003 task or malformed state can produce target Git evidence from Orc's
repository, contrary to the target-isolation acceptance criterion.

Evidence:

- `orc.py:878-899` reads the record and constructs the handoff without
  validating `target_directory` before calling `current_commit()`.
- `orc.py:228-237` passes `cwd=cwd or None`, which makes a missing target run
  `git rev-parse` in the Orc process directory.
- `orc.py:482-487` rejects a missing target only during child launch; it does
  not protect the idle-hook handoff path.
- The test suite covers missing-target launch failure at
  `tests/test_orc.py:552-555`, but has no missing-target idle-hook assertion.

Required resolution: reject or otherwise safely handle a missing/invalid
target before collecting handoff Git evidence, and add a regression test that
proves the idle hook cannot inspect Orc's repository for such a record.

Resolution:

- `current_commit()` now returns `unknown` for a missing directory, and
  `idle_hook()` rejects missing or invalid target state before Git lookup,
  normalizes the target, and passes that target explicitly to the handoff.
- A regression test verifies the malformed state is rejected without mutation.

Evidence:

- `orc.py:228-242` handles `None` without invoking Git in the caller's
  directory.
- `orc.py:883-907` validates and normalizes the idle-hook target before
  collecting commit evidence.
- `tests/test_orc.py:296-309` covers missing-target rejection and state
  preservation; `tests/test_orc.py:206-212` covers the `None` commit guard.

### R005

Status: ADDRESSED

The task commit changes `design_docs/agent_workflow.md`, but that file is not
in TASK-003's approved Scope. The change is an extra blank line before a
heading; it is unrelated to target-directory behavior and cannot be justified
as a change to the named `README.md`, tests, CI, dependency, or conditional
ignore file families. The task commit contract requires implementation content
to remain exactly within the approved Scope.

Evidence:

- `git diff --name-status HEAD^ HEAD` includes
  `M design_docs/agent_workflow.md`.
- `git diff --no-ext-diff HEAD^ HEAD -- design_docs/agent_workflow.md` shows
  only the added blank line at the existing document boundary.
- TASK-003's Scope in `design_docs/implementation_plan.md:26-57` names
  `orc.py`, `README.md`, `tests/`, the CI/dependency files, and conditional
  `.gitignore` changes, but not `design_docs/agent_workflow.md`.

Required resolution: remove the out-of-scope change from the task commit, or
have the human operator explicitly revise the task Scope before the commit is
accepted.

Resolution:

- The task retains only the single formatting change required by the exact
  documentation gate. The operator explicitly directed this required,
  formatting-only change while resolving R007.

Evidence:

- `git diff --no-ext-diff HEAD^ HEAD -- design_docs/agent_workflow.md` shows
  only the required blank line before the heading.
- No other workflow-document changes are present in the task diff.

### R006

Status: ADDRESSED

The shared task commit message does not satisfy the commit contract's 60-column
body-line limit. The violating lines are in Igor's `Implemented:` section,
which Rufus must preserve while amending the review section.

Evidence:

- `git show -s --format=%B HEAD | awk 'length($0) > 60 {print NR ":" length($0) ":" $0}'`
  reports lines 5 and 7 in the Implemented section.
- The commit contract in `design_docs/agent_workflow.md` requires all body
  lines to be at or below 60 characters.

Required resolution: Igor should rewrap the Implemented section and Rufus's
review section should remain within the 60-column limit on the next amendment.

Resolution:

- Igor rewrapped the shared commit message while preserving the required
  Implemented content, and the reviewer section also stays within the limit.

Evidence:

- The 60-column audit reports no lines over the limit for the current commit
  message.

### R007

Status: ADDRESSED

The exact documentation gate required by TASK-003 still fails after R005's
out-of-scope file removal. The baseline `design_docs/agent_workflow.md` is not
mdformat-normalized, so a clean checkout of this task cannot pass the required
`uv run mdformat --check README.md design_docs docs` command.

Evidence:

- `uv run mdformat --check README.md design_docs docs` fails with
  `File "/workspace/design_docs/agent_workflow.md" is not formatted.`
- `design_docs/agent_workflow.md` is unchanged from the planning baseline, so
  removing the task's formatting change exposes the pre-existing gate failure.
- TASK-003 acceptance criteria require this exact command to pass.

Resolution:

- Igor retained only the required formatting change in
  `design_docs/agent_workflow.md`, as explicitly directed by the operator.

Evidence:

- `uv run mdformat --check README.md design_docs docs`: PASS.
- The workflow-document diff contains only the one mdformat-required blank
  line; no unrelated workflow guidance was changed.

## Verification

- `uv sync --locked`: PASS.
- `uv run pytest -q --cov=orc --cov-report=term-missing --cov-fail-under=90`: PASS, 36 tests and 97.51% coverage.
- `uv run ruff check .`: PASS.
- `uv run ruff format --check .`: PASS.
- `uv run mypy orc.py`: PASS.
- `uv run python -m compileall -q orc.py tests`: PASS.
- `uv run mdformat --check README.md design_docs docs`: PASS.
- `uv run pip-audit --strict`: PASS.
- `actionlint .github/workflows/ci.yml`: PASS using the pinned v1.7.12
  binary downloaded by the workflow.
- `git diff --no-ext-diff --check HEAD^ HEAD`: PASS.
- The commit contains one task commit above the planning baseline and the
  worktree is clean after the review metadata update.

## Final decision

Status: COMPLETED
