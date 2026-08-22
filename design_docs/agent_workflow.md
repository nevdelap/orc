# Orc development workflow

This document defines the shared workflow for Orc's Claude and Codex
conversations. Igor implements tasks and Rufus reviews them independently.

## Task planning

`design_docs/implementation_plan.md` is the source of truth. Before changing
the product, add a `NEW` task with a complete Goal, Dependencies, Scope, and
Acceptance criteria section. Scope must identify the files or file families,
runtime modes, and platforms that are included. Acceptance criteria must state
the behavior and evidence required to call the task done.

Igor implements the first task whose state is neither `COMPLETED` nor
`BLOCKED`. A blocked task is skipped. If a task is underspecified or contains
an unresolved design decision, stop and update the plan with the human rather
than guessing.

## State transitions

Valid states are:

- `NEW`
- `IMPLEMENTED`
- `REVIEWED_FOUND_ISSUES`
- `COMPLETED`
- `BLOCKED`

Igor sets a finished implementation to `IMPLEMENTED`. Rufus sets it to
`REVIEWED_FOUND_ISSUES` when material findings remain, or to `COMPLETED` after
all findings are addressed and the review document records approval. Rufus must
not approve a task based only on an informal conclusion.

## Verification

Verification is selected from the final diff and the task's acceptance
criteria. Python source and tests must run the repository's declared test and
runtime checks once those checks are established. Until Orc's first tooling
task defines those commands, setup-only changes are verified with targeted
static checks, import/compile checks where applicable, and a clean diff review.

A passing check belongs to one exact final commit snapshot. Any subsequent
change to the relevant files invalidates that result. Never weaken a test,
remove coverage, add arbitrary sleeps or retries, or suppress failure output
to make a check pass. If the contract is ambiguous, resolve it in the plan.

## Commits

Every commit is one of:

- A task commit: `<task-id>: <plain summary>`.
- A planning commit: `Planning: <plain summary>`.
- A housekeeping commit: `HOUSEKEEPING: <plain summary>`.
- An explicitly authorized, low-risk extra commit:
  `TASK-EXTRA: <plain summary>`.

A task has one shared implementation-and-review commit. Igor creates it and
Igor and Rufus amend that same commit until the task is complete. Planning
commits define or refine tasks and never contain product implementation.

Task commits use this body:

```text
TASK-000: summary

Implemented:
- One concrete implementation or verification result.

Reviewed:
- [open] review_docs/TASK-000.md R001 - Review is pending.

Co-Authored-By: <actual-model-name> <noreply@example.com>
```

Keep the subject at or below 60 characters, wrap body lines at or below 60
characters, and keep one blank line after the subject, between role sections,
and before trailers. Build the body as one message so list items do not become
separate paragraphs. Each distinct model that performed work gets exactly one
`Co-Authored-By:` trailer using its actual model identity; roles, tools, and
providers are not model identities.

After every commit or amend, inspect the stored message and verify that the
other role's section is unchanged. If an amend loses content, recover the
exact prior message from the reflog rather than reconstructing it from memory.

## Review documents

Rufus records each review in `review_docs/<task-id>.md` and updates that same
document on later passes:

```markdown
# Review: TASK-000

## Findings

### R001

Status: OPEN

Description and evidence.

## Final decision

Status: COMPLETED
```

Findings are material only when they identify a correctness, scope,
maintainability, verification, or documentation problem. Resolved findings
remain in the document as `ADDRESSED` with evidence.

## Completion

Before handoff or completion:

- the final working tree is clean;
- the task state matches the required transition;
- the task commit message satisfies the contract;
- the acceptance and verification evidence is recorded; and
- no unrelated work is included.

Orc's bootstrap work may automate conversation setup, task selection, evidence
collection, and handoff preparation, but final implementation and review remain
separate role decisions.
