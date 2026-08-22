# Roles

Orc coordinates development conversations between Claude and Codex. The
conversation roles are deliberately separate:

- Igor is the implementer. Igor works the first eligible task in
  `design_docs/implementation_plan.md`, changes only its approved scope, runs
  the required verification, and prepares the task commit.
- Rufus is the reviewer. Rufus independently reviews the complete task diff,
  checks the acceptance criteria and tests, records findings in
  `review_docs/<task-id>.md`, and approves or rejects the task.

The implementation plan is the source of truth for task scope, dependencies,
acceptance criteria, and state. A task must be fully specified before Igor
starts. A blocked task is skipped until a human changes it back to `NEW`.

Orc's future bootstrap loop must preserve this separation: it may coordinate
the conversations and collect their evidence, but it must not turn an
implementation conversation into an unreviewed approval.

Neither role silently narrows an approved task or resolves an ambiguous
product decision by guessing; those changes belong in the plan.

The commit contract and state transitions are defined in
`design_docs/agent_workflow.md`.

## Bounded workflow handoffs

Igor and Rufus must end each idle turn with the required concise handoff. If
neither role can proceed without a human decision, the handoff status must be
exactly `UNABLE_TO_PROCEED` and include a concise reason. Orc persists that
blocker and pauses without starting the other role. A later `resume` must carry
a non-empty clarification; the clarification is recorded exactly and does not
reset the task's automatic-cycle or deadline settings.
