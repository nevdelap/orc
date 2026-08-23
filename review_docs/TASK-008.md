# Review: TASK-008

## Findings

### R001

Status: ADDRESSED

Resuming after a child failure does not clear the persisted `child_failure`.
`resume()` resets the task to `active` and launches the role again, but leaves
the old failure record in place (orc:1822-1847). `role_state()` checks that
record before checking the live session (orc:908-917), so the newly launched
role is reported as `failed` rather than `active`. This affects both roles and
violates the requirement that role state reflect the current workflow and
backend activity after resume.

Addressed evidence: `resume()` removes the stale failure after all validation
and before saving the resumed active state (orc:1839-1844). The two-role
regression test `test_resume_clears_failure_before_role_becomes_active` passes.

### R002

Status: ADDRESSED

The stop paths do not preserve the required compact status bar. When a task is
`paused`, `blocked`, or `stopped`, `poll_state()` calls `update_status()` with
only `Stopped: <reason>` (orc:1529-1537). Codex child-failure handling does the
same (orc:1600-1617), as does the Claude failure path (orc:1260-1291).
`update_status()` then renders only the task id and that message, omitting the
current task status, both role states, backend, version, and pane-switch hint.
The acceptance criteria require those segments to remain visible and refresh
after workflow stop events.

Addressed evidence: pause, blocked, and stopped paths now call
`refresh_status()` (orc:1531-1534), and Codex and Claude failure paths do the
same. `test_stop_status_keeps_compact_status_bar` and the Codex failure test
assert the complete status fields; the full suite passes.

### R003

Status: ADDRESSED

Codex child exit status is ignored whenever a handoff has already changed the
workflow phase. `poll_children()` sets `expected_handoff` solely from the
phase (orc:1581-1583), and only records `child_failure` when the phase still
matches the exiting role (orc:1599-1612). Therefore a Codex process that exits
non-zero after emitting a valid handoff is treated as an expected completion,
even though the task requires real non-zero or unexpected child exits to retain
the existing failure stop behavior. The new retirement path must distinguish a
normal retired child from an unretired failed child.

Addressed evidence: retired sessions are handled before exit-status checks,
while every unretired non-zero Codex exit records `child_failure`
(orc:1562-1577). `test_codex_nonzero_exit_after_handoff_is_child_failure` passes.

### R004

Status: ADDRESSED

The task commit message violates the mandatory commit contract's body line
limit. `git show -s --format=%B HEAD` reports Implemented-section lines of 61,
62, 65, 66, and 70 characters, while
`design_docs/agent_workflow.md` requires every body line to be at or below 60
characters. This is a completion blocker independent of the runtime checks.

Addressed evidence: the amended Implemented section is wrapped to the required
limit, and the commit-message contract audit passes with one model trailer.

## Final decision

Status: COMPLETED

The implementation is approved. R001-R004 are addressed in the shared
TASK-008 commit, and the applicable verification passes on its final snapshot.
