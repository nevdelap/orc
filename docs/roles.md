# Roles

Orc coordinates development conversations between Claude and Codex. The
conversation roles are deliberately separate:

- Igor is the implementer. Igor works the first eligible task in
  `design_docs/implementation_plan.md`, changes only its approved scope, runs
  the required verification, and prepares the task commit.
- Rufus is the reviewer. Rufus independently reviews the complete task diff,
  checks the acceptance criteria and tests, records findings in
  `review_docs/<task-id>.md`, and approves or rejects the task.

The final non-blank line of every agent turn is the strict
`ORC_HANDOFF_V1: <JSON object>` contract with exactly the fields
`launch_token`, `status`, `summary`, `files_changed`, `verification`,
`blockers`, and `requested_action`. Igor may emit `HANDOFF` or
`UNABLE_TO_PROCEED`; Rufus may also emit `COMPLETE`. Orc validates the launch
token, role, generation, round, phase, and backend session before recording a
handoff. A receiver gets only the preceding validated canonical handoff in a
delimited context block, never raw backend payload data.

The contract is bounded: the complete frame and delivered context are at most
16 KiB, launch tokens are at most 256 UTF-8 bytes, scalar fields at most 4 KiB,
list items at most 512 bytes, and each handoff list contains at most 32 items.
The persisted handoff history retains at most 128 accepted entries, preserving
the newest entry for each role when older entries are evicted. Oversized or
duplicate-key handoffs are rejected as a whole and cannot alter workflow state
or enter a prompt.

Claude stream lines and events are limited to 64 KiB. Malformed or oversized
events are discarded through the end of the event and produce one bounded
rejected diagnostic. A child retains at most 256 stream events in memory;
older events are dropped and `stream_dropped_count` saturates at 1,000,000.
Explicit operator requests are retained in `user_requests` and
`last_user_request`, with at most 32 entries and 4 KiB per UTF-8 request.
Over-limit requests are rejected before state mutation or launch. Generated
prompts are ephemeral, capped at 32 KiB, and reduce optional handoff context
before launch; an explicit request is never silently truncated. Rejected
diagnostics retain at most 64 entries and 4 KiB per diagnostic.

Schema-3 task records also retain a chronological `audit_events` list capped
at 256 entries, monotonic `audit_next_sequence`, saturating
`audit_dropped_count`, `last_terminal_event_key`, and bounded task/generation
timing totals. Audit events are appended under the state lock in the same
revisioned atomic write as the state decision. They record only safe role,
round, generation, status/phase, stop-reason, timestamp, and bounded
diagnostic data; prompts, launch tokens, backend arguments, raw payloads, and
transcripts are redacted and never persisted in the audit trail. Open timing
generations are never evicted; a full set of open generations rejects a launch
with `timing generation retention full` before child spawn.

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
