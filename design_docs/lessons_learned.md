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
- Automatic workflow tests must cover the complete handoff lifecycle: an
  idle notification, retirement of the old PTY child, launch of the next role,
  and the next round. A live child after a handoff is normal completion, not
  evidence that the next role can be skipped.
- Persisted failure metadata belongs to a specific workflow generation. A
  validated resume must clear or supersede stale failure state before the
  relaunch, while an unretired child that exits unexpectedly must still stop
  the current workflow.
- Backend session identities are role-specific. A reviewer must never inherit
  an implementer's session, and backend exit status must be checked before a
  handoff-shaped response is accepted.
- Agentbox integration requires exact argv and real PTY coverage for both
  marker states, both roles, begin/resume, and executable paths containing
  spaces; command-construction unit tests alone are insufficient.

## Verification and commit discipline

- Commit-message formatting is a repository gate: keep every body line at or
  below 60 columns and retain the shared `Implemented:`, `Reviewed:`, and
  model-trailer contract through every amendment.
- A completed task is not ready for housekeeping until its final review
  records the exact verification snapshot, including integration coverage,
  documentation checks, security/audit checks, and a clean worktree.

## Housekeeping

- Bootstrap work may appear in the worktree while the next task is being
  created; record that transition explicitly rather than misclassifying it as
  an unrelated product change.
- Before retiring completed reviews, capture their durable lessons here and
  retain the original commits in Git for history and auditability.
