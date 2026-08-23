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

## Workflow-resilience follow-up opportunities

### Codex capability preflight

Orc probes Claude's required print/stream/resume interface before launch, but
does not equivalently verify the Codex command's notify, configuration, and
resume contract. A future task should define an explicit Codex capability
check, version/error diagnostics, and tests using compatible and incompatible
fake executables.

### Signal-safe cleanup

`Ctrl-Q` performs the normal TUI cleanup path, but terminal disconnects,
`SIGINT`, `SIGHUP`, and an unexpected Orc process exit need an explicitly
specified best-effort cleanup policy. A future task should preserve state,
retire child process groups safely, close PTY readers/descriptors, and test
the relevant Linux signal and parent-exit cases.

### Bounded workflow audit trail

The mutable task record is insufficient for post-failure diagnosis. A future
task could define a bounded, append-only audit history for launches, accepted
and rejected handoffs, state transitions, child exits, and cleanup decisions.
It must state retention, redaction, atomicity, and operator-display rules.

### Bounds for agent-controlled data

Handoffs, backend events, diagnostics, and injected recipient context need
explicit maximum sizes and item counts. A future task should define safe
truncation, preservation of useful summary/diagnostic information, and tests
for excessive or malformed input without unbounded state growth or prompts.

### Stronger Git evidence

A short commit hash at handoff does not establish whether the target worktree
was clean or which files remained uncommitted. A future task could record a
bounded Git evidence snapshot: HEAD, branch, clean/dirty state, and a changed
file summary, with timeout and non-Git handling.

### Read-only task-status command

An `orc status TASK-ID` command could expose current state, recent accepted
and rejected events, diagnostics, and lifecycle metadata without opening the
TUI. A future task must define its stable output, redaction, exit statuses, and
behavior for missing, corrupt, or locked state.

### Stalled-agent health indication

The deadline limits a whole cycle but does not distinguish a working agent
from one with no PTY activity. A future task could display non-invasive
last-activity/stalled health information, while avoiding automatic termination
of legitimate long-running work unless separately and explicitly authorized.
