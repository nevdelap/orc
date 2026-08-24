# Review: task-014

## Findings

### R001

Status: ADDRESSED

Malformed persisted argv can escape the required bounded preflight diagnostic.
`backend_command_value()` accepts executable strings containing an embedded NUL,
and `_run_preflight_probe()` catches `OSError` from `subprocess.Popen()` but not
`ValueError`. A CLI or in-place resume with a valid schema-v2 record containing
such a command therefore raises `ValueError: embedded null byte` instead of a
backend-specific diagnostic identifying the failed probe. This violates the
malformed launch-configuration requirement and makes the failure path
observable as an uncaught traceback.

Evidence:

- `orc:backend_command_value` validates non-empty strings but does not reject
  embedded NUL bytes.
- `orc:_run_preflight_probe` catches only `OSError` around `Popen`.
- Direct probe evidence on `bf0b357`: `probe_codex(['bad\\x00command'])`
  raises `ValueError('embedded null byte')`.

Resolution:

- `_run_preflight_probe()` now catches both `OSError` and `ValueError` from
  `Popen` and converts them to the bounded backend/probe diagnostic.

Evidence:

- `tests/test_task014.py:test_malformed_executable_argv_has_bounded_backend_diagnostic`
  passes on the reviewed commit.

### R002

Status: ADDRESSED

The agentbox permission flag is not guaranteed to occur exactly once. Both
`add_agentbox_codex_flag()` and `add_agentbox_claude_flag()` only add the flag
when it is absent; if a configured argv already contains the same option more
than once, all duplicates remain in the final launch argv. Schema-v2 state
accepts list-valued `backend_command`, so this is reachable through persisted
configuration as well as direct argv construction. The task requires the
backend-specific no-permissions flag to remain present exactly once after a
successful preflight.

Evidence:

- `orc:add_agentbox_codex_flag` and `orc:add_agentbox_claude_flag` test only
  `flag not in command` before insertion and never deduplicate.
- Direct function evidence on `bf0b357` with Linux marker state and two
  pre-existing Codex flags returns a command containing two flags.
- The added test covers one pre-existing flag, not duplicate pre-existing
  occurrences.

Resolution:

- Both agentbox flag builders now remove all existing copies before inserting
  exactly one flag before the final prompt.

Evidence:

- `tests/test_task014.py:test_agentbox_flag_is_deduplicated` covers both
  Codex and Claude with duplicate configured flags.

### R003

Status: ADDRESSED

Capability checks use substring matching rather than literal-token matching.
`_required_help_tokens()` accepts `--printish` for `--print`,
`--configurator` for `--config`, `SESSION_ID_SUFFIX` for `SESSION_ID`, and
`PROMPTING` for `PROMPT`. An incompatible executable can therefore pass the
preflight while lacking the required launch contract, contrary to the plan's
literal-token requirement.

Evidence:

- `orc:_required_help_tokens` uses `token in text` for every requirement.
- Direct evidence on `bf0b357`: a Claude help string containing only
  `--printish`, `--output-formatters`, `stream-jsonx`, `--input-format`,
  `textish`, and `--resumeable` reports no missing capabilities.

Resolution:

- `_required_help_tokens()` now tokenizes help output and compares exact
  option, identifier, and bracketed-identifier tokens.

Evidence:

- `tests/test_task014.py:test_help_capabilities_require_literal_tokens`
  verifies near-match tokens are rejected.

### R004

Status: ADDRESSED

The acceptance test matrix does not prove failure preservation for both resume
paths and both backends. The new tests cover compatible CLI resume for both
backends, incompatible in-place resume only for Claude, and direct probe
failure modes, but do not exercise CLI-resume or Codex in-place failure with
state/child-set invariants, nor OSError preservation through either resume
entry point. The task explicitly requires begin, CLI resume, and in-place
resume coverage for both backends, with failed probes leaving state and child
processes unchanged.

Evidence:

- `tests/test_task014.py:test_cli_resume_preflights_before_mutating_state`
  covers only compatible backends.
- `tests/test_task014.py:test_in_place_resume_preflights_before_mutating_or_launching`
  covers only an incompatible Claude help probe.
- `tests/test_task014.py:test_preflight_version_failures_are_rejected` and
  `test_preflight_timeout_is_bounded` call the probe directly and do not check
  resume state or child invariants; no OSError resume-preservation test is
  present.

Resolution:

- Added CLI and in-place resume tests for both backends covering incompatible
  help and missing-executable failures, with state and launch invariants.

Evidence:

- `test_cli_resume_failure_preserves_state_and_children`,
  `test_cli_resume_oserror_preserves_state_and_children`,
  `test_in_place_resume_failure_preserves_state_and_children`, and
  `test_in_place_resume_oserror_preserves_state_and_children` pass.

## Final decision

Status: COMPLETED
