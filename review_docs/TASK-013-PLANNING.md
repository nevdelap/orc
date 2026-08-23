# Review: TASK-013 planning

## Findings

### R001

Status: ADDRESSED

The planning commit does not satisfy the commit contract. Its two
`Implemented:` list items are longer than 60 characters, and the
`Co-Authored-By: Codex` trailer identifies a role/tool rather than the actual
model name, version, and variant. The implementer must wrap the owned list
items and replace the trailer with the required actual model attribution.

Resolution:

- The Implemented and Reviewed lists are wrapped at 60 characters, and the
  trailer identifies GPT-5.

### R002

Status: ADDRESSED

The resume requirement in `design_docs/implementation_plan.md:450-459`
requires “one documented resume policy” but does not define that policy. It
does not specify, for each status and stop reason, eligibility, validation,
fields to reset or preserve, deadline/round behavior, or the exact diagnostic
for rejection. Consequently, the CLI and in-place implementations cannot be
held to the required equivalence without inventing product behavior. Enumerate
those cases in Scope and Acceptance criteria, including active and every
inconsistent record shape.

Resolution:

- Scope now defines the resume status, stop-reason, preservation, reset,
  deadline, role, round, and diagnostic matrix.

### R003

Status: ADDRESSED

The backend correlation requirement at
`design_docs/implementation_plan.md:474-485` says to read documented,
explicitly named Codex and Claude fields, but names none of the payload paths,
message types, or session/thread sources. This leaves the critical security
and state-transition mapping to implementer inference and makes the required
cross-backend tests non-reproducible. Specify the exact fields and accepted
message forms for each adapter, including how each produces the canonical
handoff and identity.

Resolution:

- Scope names the accepted root fields, aliases, event types, session
  matching, message extraction, and rejection behavior for both adapters.

### R004

Status: ADDRESSED

The quality gate at `design_docs/implementation_plan.md:522-528` and its
acceptance criterion at `:563-566` require branch coverage of at least 90%
and a Linux GitHub Actions workflow, but do not specify the coverage command,
source/configuration target, threshold-enforcement mechanism, report path, or
workflow file/job invocation. “Document the matching local commands” cannot
repair those omissions because the implementation is supposed to be bounded
by this plan. Pin the exact local and CI commands and their measured target.

Resolution:

- Scope now pins the local commands, CI jobs, coverage options and report,
  locked environment, failure threshold, and diagnostic artifacts.

### R005

Status: ADDRESSED

The added matrix supplies the missing role/session predicates, but the prose
policy at `design_docs/implementation_plan.md:464-475` still says that a
`stopped` `child_failure` case that does not match the single-failed-role rule
“otherwise resumes Igor at round 1”. The normative table at `:490-491` rejects
all other inconsistent combinations. These requirements conflict, so the
implementer still cannot know whether an unmatched child failure is eligible.

Required resolution:

- Remove the conflicting fallback or add an explicit eligible matrix row for
  it, so every child-failure combination has one result.

Resolution:

- The prose now rejects every child-failure combination outside the single
  failed-role matrix row, matching the normative table.

### R006

Status: ADDRESSED

The plan now gives numeric limits, but it does not define overflow behavior.
“Cap” does not say whether an oversized handoff is rejected or safely
truncated, and “at most 256” receipts conflicts with never evicting a receipt
while its generation can still report. If more than 256 generations remain
eligible or live, the implementation has no bounded, deterministic behavior.

Required resolution:

- Specify reject/truncate behavior for every size limit and define what Orc
  does when the receipt cap is full of live or still-reporting generations.

Resolution:

- Scope now rejects oversized handoffs, truncates diagnostic details with a
  marker, evicts only eligible entries, and stops safely when all receipt
  slots are occupied by live or still-reporting generations.

### R007

Status: ADDRESSED

The strict handoff schema at `design_docs/implementation_plan.md:499-512`
still says only that “list fields” are JSON lists of strings. It does not
identify which of `files_changed`, `verification`, or `blockers` are lists, or
define the types and empty-value rules for `launch_token`, `status`,
`summary`, and `requested_action`. The parser and fixtures can therefore
still diverge while each claims to implement the exact schema.

Required resolution:

- Specify the complete field/type/requiredness table, including which lists
  may be empty and the status-specific blocker rules.

Resolution:

- Scope now defines all seven fields, their JSON types, requiredness, limits,
  allowed empty lists, and status-specific blocker rules.

## Final decision

Status: PLANNING_APPROVED
