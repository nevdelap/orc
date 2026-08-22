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

## Verification

- `git diff --no-ext-diff --check HEAD^ HEAD`: PASS.
- Commit subject and body lines are at or below 60 characters: PASS.
- The plan keeps TASK-003 in the valid `NEW` state: PASS.
- No product-runtime gates were applicable because this planning diff changes
  no application source or tests.

## Final decision

Status: PLANNING_APPROVED
