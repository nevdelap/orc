# Review: task-022

## Findings

### R001

Status: ADDRESSED

The prior finding was that ineligible Ctrl-R was forwarded to the selected
child instead of being consumed.

Evidence:

- `orc:3957-3960` now always stops Ctrl-R after attempting to open the
  prompt, including an unsuccessful attempt.
- `tests/test_orc.py:test_ineligible_ctrl_r_is_consumed_without_child_write`
  verifies the no-op path.

Resolution:

- Ctrl-R is now consumed for both eligible and ineligible outcomes.

### R002

Status: ADDRESSED

The prior finding was that a child exit between liveness selection and the
PTY write could lose input instead of using the required fallback child.

Evidence:

- `orc:3572-3613` retries `EIO`, `EPIPE`, `EBADF`, partial, and zero-write
  failures using the deterministic fallback order and retains selection.
- `tests/test_orc.py:test_pty_write_race_retries_fallback_and_keeps_selection`
  covers the failed selected write and fallback pane scrolling.
- `tests/test_orc.py:test_real_pty_selected_routing_and_exit_race_fallback`
  covers selected-role routing and a closed PTY master with a live fallback.

Resolution:

- Failed selected writes now retry the remaining bytes through the specified
  fallback order, move the fallback pane to the bottom, and retain the
  unified selection.

### R003

Status: ADDRESSED

The prior finding was that required Linux real-PTY acceptance cases were
missing, including child-failure Ctrl-R, unlaunched-pane rejection, failed
next-child launch, and no-live-child behavior.

Evidence:

- `tests/test_orc.py:520-757` now exercises selected-role routing, the
  child-exit write race, unlaunched-pane rejection, no-live-child input,
  failed next-child launch, reader cleanup, reaping, and persisted failure.
- `tests/test_orc.py:762-846` covers all eight resumable outcomes,
  including a valid `child_failure` record, with a real PTY launching the
  selected reviewer role.
- Profile B passes 39 integration tests on the final implementation
  snapshot.

Resolution:

- Focused Linux real-PTY/subprocess coverage now includes the previously
  missing routing, launch, cleanup, failure, and resume cases.

### R004

Status: ADDRESSED

The prior finding was that README omitted `orchestrator_exit` from its
stop-reason list while documenting it as resumable.

Evidence:

- `README.md:163-165` documents `orchestrator_exit` as resumable.
- `README.md:216-220` now includes `orchestrator_exit` in the stop-reason
  list.
- `design_docs/agent_workflow.md` and `orc` include
  `orchestrator_exit` in the normative stop-reason set.

Resolution:

- README now lists the complete stop-reason set consistently.

### R005

Status: ADDRESSED

The prior finding was that a write race marked a child exited without
allowing normal polling to close the reader, reap the child, or record
`child_failure`.

Evidence:

- `orc:3599-3615` now marks `write_failed`, closes the PTY reader and fd,
  and leaves `exited` false so `poll_children()` still waits for the child.
- `orc:3847-3907` reaps the child and records the active workflow's
  `child_failure` through the normal state transition.
- `tests/test_orc.py:test_real_pty_write_failure_is_reaped_and_records_child_failure`
  proves reader removal, fd closure, persisted failure, and that no zombie
  remains after polling.

Resolution:

- Write failures preserve polling state while routing remaining bytes to the
  deterministic fallback; polling performs cleanup and failure processing.

## Final decision

Status: COMPLETED
