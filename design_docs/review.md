# Deferred rescue findings

This document is a holding area for rescue findings discovered outside an
approved task. It is not an implementation plan, task specification, review
decision, or authorization to change Orc. Igor and Rufus must ignore these
findings while selecting, implementing, or reviewing work.

A human must first turn a finding into a fully specified `NEW` task in
`design_docs/implementation_plan.md`, with Goal, Dependencies, Scope, and
Acceptance criteria. Only that approved task authorizes implementation. Move
or remove a finding from this document when its resulting task has been
planned; do not treat its presence here as a task state or dependency.

All findings previously held here have been promoted to fully specified `NEW`
tasks in `design_docs/implementation_plan.md`. This file remains a holding
area for future rescue findings; it is not an implementation plan, task
specification, review decision, or authorization to change Orc.

## Future ideas

- Add `orc list` to show task IDs and their current states, making it easier
  to choose future task IDs without collisions.
- Add `orc rm <taskid> <taskid> ...` to clean up old task records. It should
  also accept regular-expression selectors; matching, locking, confirmation,
  and recovery behavior must be specified before implementation.
- Harden Ctrl-R so it is available from every state with no active Igor or
  Rufus. Recovery after a deadline, maximum-cycle stop, or error should always
  be possible in place without restarting `orc`.
