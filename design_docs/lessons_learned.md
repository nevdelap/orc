# Lessons Learned

This document records durable implementation, verification, and process
lessons from completed Orc tasks. It complements
`design_docs/agent_workflow.md` and `docs/roles.md`.

## Task and review discipline

- Scope and acceptance criteria must identify the exact files, runtime modes,
  and evidence required before implementation begins.
- The implementer and reviewer share one task commit. Review findings stay in
  the review document, and resolved findings remain recorded as `ADDRESSED`
  with evidence until the task is retired during housekeeping.
- Review the complete final commit against its parent and keep unrelated
  changes out of the task snapshot.
- A clean worktree and an explicitly recorded plan state are completion
  requirements, not informal cleanup.

## Orc runtime and handoffs

- Saved implementer and reviewer sessions must receive their role-specific
  continuation, review, and handoff prompts when resumed.
- Handoffs should retain the final response together with UTC and local time,
  task, role, round, thread ID, and current commit hash.
- Interactive PTY/TUI behavior needs focused checks for lifecycle attachment,
  resize, input forwarding, ANSI color preservation, and pane focus.
- Validate and normalize a target directory before collecting any Git evidence;
  a missing target must never fall back to Orc's process directory.
- Derive child PTY dimensions from each rendered pane after layout and resize,
  and cover the live path with a real PTY test rather than only unit checks.
- Treat global shortcuts as part of the input contract: reserve only keys
  needed by Orc and verify that all other control and text input reaches the
  active child.
- Record manual UI acceptance against an exact commit, terminal environment,
  size matrix, scenario, observation, and result so review amendments cannot
  make the evidence ambiguous.

## Housekeeping

- Bootstrap work may appear in the worktree while the next task is being
  created; record that transition explicitly rather than misclassifying it as
  an unrelated product change.
- Before retiring completed reviews, capture their durable lessons here and
  retain the original commits in Git for history and auditability.
