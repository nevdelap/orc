from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

ORC_SOURCE = Path(__file__).parents[1] / "orc"
spec = importlib.util.spec_from_loader(
    "orc_task016", SourceFileLoader("orc_task016", str(ORC_SOURCE))
)
assert spec is not None and spec.loader is not None
orc = importlib.util.module_from_spec(spec)
sys.modules["orc_task016"] = orc
spec.loader.exec_module(orc)


def canonical(
    token: str = "token",
    *,
    status: str = "HANDOFF",
    blockers: list[str] | None = None,
) -> dict[str, object]:
    return {
        "launch_token": token,
        "status": status,
        "summary": "summary",
        "files_changed": [],
        "verification": [],
        "blockers": [] if blockers is None else blockers,
        "requested_action": "continue",
    }


def handoff_message(value: dict[str, object]) -> str:
    return orc.HANDOFF_PREFIX + json.dumps(value, ensure_ascii=False)


def test_handoff_frame_and_unicode_byte_boundaries() -> None:
    value = canonical()
    value["summary"] = "é" * 2049
    with pytest.raises(ValueError, match="4 KiB"):
        orc.parse_handoff_message(
            handoff_message(value), role="implementer", launch_token="token"
        )
    value["summary"] = "é" * 2048 + "a"
    with pytest.raises(ValueError, match="4 KiB"):
        orc.parse_handoff_message(
            handoff_message(value), role="implementer", launch_token="token"
        )

    duplicate = (
        orc.HANDOFF_PREFIX
        + '{"launch_token":"token","status":"HANDOFF",'
        + '"summary":"s","summary":"s","files_changed":[],'
        + '"verification":[],"blockers":[],"requested_action":"a"}'
    )
    with pytest.raises(ValueError, match="duplicate"):
        orc.parse_handoff_message(duplicate, role="implementer")


def test_context_reduces_optional_data_and_keeps_blocker() -> None:
    value = canonical(status=orc.UNABLE_TO_PROCEED, blockers=["must wait"])
    value["summary"] = "s" * 4096
    value["requested_action"] = "r" * 4096
    value["files_changed"] = ["f" * 512] * 32
    value["verification"] = ["v" * 512] * 32
    context = orc.handoff_context(
        {"handoffs": [{"role": "implementer", "canonical": value}]},
        "implementer",
    )
    assert len(context.encode()) <= orc.HANDOFF_FRAME_LIMIT
    assert "must wait" in context
    assert "truncated" in context


def test_user_requests_are_bounded_without_truncating_new_request() -> None:
    record: dict[str, object] = {"user_requests": [str(index) for index in range(32)]}
    orc.append_user_request(record, "new request")
    assert len(record["user_requests"]) == orc.USER_REQUEST_LIMIT
    assert record["user_requests"][-1] == "new request"
    assert record["last_user_request"] == "new request"
    with pytest.raises(SystemExit, match="4 KiB"):
        orc.append_user_request(record, "é" * 2049)


def test_handoff_history_protects_other_role_and_rejects_full_history() -> None:
    handoffs = [
        {"role": "implementer", "canonical": canonical(str(index))}
        for index in range(orc.HANDOFF_HISTORY_LIMIT - 1)
    ]
    handoffs.append({"role": "reviewer", "canonical": canonical("review")})
    record: dict[str, object] = {"handoffs": handoffs}
    assert orc.append_handoff(
        record, {"role": "implementer", "canonical": canonical("new")}
    )
    assert len(record["handoffs"]) == orc.HANDOFF_HISTORY_LIMIT
    assert record["handoffs"][-1]["canonical"]["launch_token"] == "new"
    assert any(
        entry["canonical"]["launch_token"] == "review" for entry in record["handoffs"]
    )

    full = {
        "handoffs": [
            {"role": "implementer", "canonical": canonical(str(index))}
            for index in range(orc.HANDOFF_HISTORY_LIMIT)
        ]
    }
    assert orc.append_handoff(
        full, {"role": "implementer", "canonical": canonical("rejected")}
    )
    assert len(full["handoffs"]) == orc.HANDOFF_HISTORY_LIMIT


def test_claude_stream_is_line_bounded_and_retained() -> None:
    session = orc.ChildSession("reviewer", 1, -1, object(), strict_protocol=True)
    for index in range(orc.STREAM_EVENT_RETENTION + 10):
        event = {
            "type": "system",
            "session_id": str(index),
        }
        orc.OrcApp.read_claude_stream(session, json.dumps(event).encode() + b"\n")
    assert len(session.stream_events) == orc.STREAM_EVENT_RETENTION
    assert session.stream_dropped_count == 10
    assert session.stream_events[0]["session_id"] == "10"

    oversized = b"{" + b"x" * orc.STREAM_EVENT_LIMIT + b"\n"
    orc.OrcApp.read_claude_stream(session, oversized)
    assert len(session.stream_line_bytes) == 0
    assert session.stream_rejected_diagnostics
    assert all(
        len(item.encode()) <= orc.DIAGNOSTIC_LIMIT
        for item in session.stream_rejected_diagnostics
    )


def test_state_duplicate_keys_and_bounded_diagnostic(tmp_path: Path) -> None:
    state = tmp_path / "state.json"
    state.write_text('{"TASK-016": {"x": 1, "x": 2}}')
    with pytest.raises(orc.StateFormatError, match="duplicate"):
        orc._read_state(state)

    record: dict[str, object] = {"rejected_events": []}
    orc.record_rejected_event(record, "x" * (orc.DIAGNOSTIC_LIMIT + 1))
    assert len(record["rejected_events"]) == 1
    assert len(record["rejected_events"][0]["reason"].encode()) <= (
        orc.DIAGNOSTIC_LIMIT
    )


def state_record(tmp_path: Path) -> dict[str, object]:
    return {
        "schema_version": orc.STATE_SCHEMA_VERSION,
        "revision": 1,
        "task_id": "TASK-016",
        "status": "active",
        "phase": "implementer",
        "round": 1,
        "target_directory": str(tmp_path),
        "backend": "codex",
        "backend_command": "codex",
        "user_requests": [],
        "handoffs": [],
        "event_receipts": [],
        "rejected_events": [],
        "role_states": {"implementer": "active", "reviewer": "inactive"},
        "role_launches": {},
        "role_generations": {"implementer": 0, "reviewer": 0},
        "max_rounds": 5,
        "deadline_seconds": 3600,
        "automatic_rounds": True,
        "deadline_at": "2099-01-01T00:00:00+00:00",
        "stop_reason": None,
        "audit_events": [],
        "audit_next_sequence": 1,
        "audit_dropped_count": 0,
        "last_terminal_event_key": None,
        "timing": {
            "task_started_at": "2025-01-01T00:00:00Z",
            "task_finished_at": None,
            "wall_seconds": 0,
            "agent_wall_seconds": {"implementer": 0, "reviewer": 0},
            "unattributed_wall_seconds": 0,
            "generations": [],
        },
    }


@pytest.mark.parametrize(
    "change",
    [
        lambda value: value.update({"backend_command": "x" * 4097}),
        lambda value: value.update({"user_requests": ["x"] * 33}),
        lambda value: value.update({"user_requests": ["é" * 2049]}),
        lambda value: value.update({"handoffs": [{}] * 129}),
        lambda value: value.update({"last_user_request": "x" * 4097}),
        lambda value: value.update({"prompt": "x" * 4097}),
        lambda value: value.update(
            {"rejected_events": [{"reason": "x" * (orc.DIAGNOSTIC_LIMIT + 1)}]}
        ),
        lambda value: value.update(
            {"handoffs": [{"role": "implementer", "canonical": {"status": "HANDOFF"}}]}
        ),
        lambda value: value.update(
            {
                "role_launches": {
                    "implementer": {
                        "phase": "implementer",
                        "generation": 1,
                        "launch_token": "token",
                        "session_id": "x" * 4097,
                    }
                }
            }
        ),
        lambda value: value.update(
            {"launch_history": [{"role": "implementer", "generation": 1}] * 257}
        ),
        lambda value: value.update({"processed_idle_events": ["x"] * 257}),
    ],
)
def test_state_model_rejects_each_new_unbounded_field(
    tmp_path: Path, change: object
) -> None:
    value = state_record(tmp_path)
    change(value)  # type: ignore[operator]
    with pytest.raises(orc.StateFormatError):
        orc._validate_state_document({"TASK-016": value}, tmp_path / "state.json")


def test_handoff_parser_rejects_every_disposition_and_shape_error() -> None:
    base = canonical()
    cases = [
        ({**base, "launch_token": ""}, "non-empty"),
        ({**base, "status": "OTHER"}, "not allowed"),
        ({**base, "files_changed": "bad"}, "list"),
        ({**base, "files_changed": [""]}, "invalid"),
        ({**base, "files_changed": ["x" * 513]}, "512"),
        ({**base, "files_changed": ["x"] * 33}, "32"),
        ({**base, "status": orc.UNABLE_TO_PROCEED}, "requires blockers"),
    ]
    for value, message in cases:
        with pytest.raises(ValueError, match=message):
            orc.parse_handoff_message(
                handoff_message(value), role="implementer", launch_token="token"
            )
    with pytest.raises(ValueError, match="does not match"):
        orc.parse_handoff_message(
            handoff_message(base), role="implementer", launch_token="other"
        )
    with pytest.raises(ValueError, match="only Rufus"):
        orc.parse_handoff_message(
            handoff_message({**base, "status": "COMPLETE"}),
            role="implementer",
            launch_token="token",
        )
    with pytest.raises(ValueError, match="empty"):
        orc.parse_handoff_message(
            handoff_message({**base, "status": "COMPLETE", "blockers": ["blocked"]}),
            role="reviewer",
            launch_token="token",
        )
    with pytest.raises(ValueError, match="invalid ORC"):
        orc.parse_handoff_message(orc.HANDOFF_PREFIX + "not-json", role="implementer")


def test_context_and_prompt_bounds_have_explicit_failure_paths() -> None:
    huge = canonical()
    huge["launch_token"] = "x" * (orc.HANDOFF_FRAME_LIMIT + 1)
    with pytest.raises(ValueError, match="required handoff"):
        orc.handoff_context(
            {"handoffs": [{"role": "implementer", "canonical": huge}]},
            "implementer",
        )
    with pytest.raises(ValueError, match="generated prompt"):
        orc.ensure_prompt_bound("x" * (orc.GENERATED_PROMPT_LIMIT + 1))
    assert orc.ensure_prompt_bound("ok") == "ok"
    assert "No validated" in orc.handoff_context({"handoffs": []}, "reviewer")


@pytest.mark.parametrize("backend", ["codex", "claude"])
def test_backend_metadata_cannot_overflow_prompt_limit(
    tmp_path: Path, backend: str
) -> None:
    with pytest.raises(ValueError, match="generated prompt"):
        orc.backend_launch_command(
            backend,
            [backend],
            "x" * orc.GENERATED_PROMPT_LIMIT,
            "TASK-016",
            "implementer",
            None,
            False,
            False,
            tmp_path / "state.json",
        )


def test_requests_and_history_reject_invalid_direct_inputs() -> None:
    with pytest.raises(SystemExit, match="non-empty"):
        orc.validate_user_request("")
    with pytest.raises(SystemExit, match="invalid persisted"):
        orc.append_user_request({"user_requests": [3]}, "request")
    full: dict[str, object] = {"handoffs": [3] * orc.HANDOFF_HISTORY_LIMIT}
    assert not orc.handoff_slot_available(full, "implementer")
    assert not orc.append_handoff(
        full, {"role": "implementer", "canonical": canonical("rejected")}
    )
    with pytest.raises(SystemExit, match="invalid persisted"):
        orc.append_handoff({"handoffs": "bad"}, {"role": "implementer"})
    record: dict[str, object] = {"rejected_events": []}
    for index in range(orc.REJECTED_DIAGNOSTIC_LIMIT + 4):
        orc.record_rejected_event(record, str(index))
    assert len(record["rejected_events"]) == orc.REJECTED_DIAGNOSTIC_LIMIT


def test_codex_payload_limits_and_stream_malformed_event_diagnostics() -> None:
    with pytest.raises(ValueError, match="64 KiB"):
        orc.parse_codex_idle_payload(
            {
                "last-assistant-message": "x" * (orc.CODEX_PAYLOAD_LIMIT + 1),
                "thread-id": "t",
            }
        )
    with pytest.raises(ValueError, match="256 bytes"):
        orc.parse_codex_idle_payload(
            {"last-assistant-message": "ok", "thread-id": "x" * 257}
        )
    session = orc.ChildSession("reviewer", 1, -1, object(), strict_protocol=True)
    orc.OrcApp.read_claude_stream(session, b"{" + b"x" * 8)
    assert len(session.stream_line_bytes) > 0
    orc.OrcApp.read_claude_stream(session, b"\n")
    orc.OrcApp.read_claude_stream(session, b"{bad}\n[1]\n\xff\n")
    assert len(session.stream_rejected_diagnostics) >= 3
    session.stream_dropped_count = orc.STREAM_DROPPED_LIMIT
    session.stream_events = []
    for index in range(orc.STREAM_EVENT_RETENTION + 1):
        orc.OrcApp.read_claude_stream(
            session,
            (json.dumps({"type": "system", "session_id": str(index)}) + "\n").encode(),
        )
    assert session.stream_dropped_count == orc.STREAM_DROPPED_LIMIT


def test_strict_stream_protocol_errors_are_bounded() -> None:
    session = orc.ChildSession("reviewer", 1, -1, object(), strict_protocol=True)
    events = [
        {"type": "system"},
        {"type": "system", "session_id": "one"},
        {"type": "system", "session_id": "two"},
        {"type": "result", "session_id": "two", "result": "ok"},
        {"type": "result", "session_id": "two"},
        {"type": "result", "session_id": "two", "result": ""},
        {"type": "result", "is_error": True, "session_id": "two", "result": "x"},
    ]
    for event in events:
        orc.OrcApp.read_claude_stream(session, json.dumps(event).encode() + b"\n")
    assert session.stream_error == "Claude stream reported an error"


def test_canonical_validator_and_utf8_truncation_edges(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="object"):
        orc._validate_canonical_handoff([])
    with pytest.raises(ValueError, match="schema mismatch"):
        orc._validate_canonical_handoff({"status": "HANDOFF"})
    oversized = canonical()
    oversized["launch_token"] = "x" * (orc.HANDOFF_TOKEN_LIMIT + 1)
    with pytest.raises(ValueError, match="256"):
        orc._validate_canonical_handoff(oversized)
    bad_status = canonical(status="OTHER")
    with pytest.raises(ValueError, match="not allowed"):
        orc._validate_canonical_handoff(bad_status)
    bad_list = canonical()
    bad_list["files_changed"] = "not a list"
    with pytest.raises(ValueError, match="32"):
        orc._validate_canonical_handoff(bad_list)
    unable = canonical(status=orc.UNABLE_TO_PROCEED)
    with pytest.raises(ValueError, match="requires blockers"):
        orc._validate_canonical_handoff(unable)
    complete = canonical(status="COMPLETE", blockers=["blocker"])
    with pytest.raises(ValueError, match="empty"):
        orc._validate_canonical_handoff(complete)
    assert orc._truncate_utf8("é", 2) == "é"
    assert orc._truncate_utf8("xx", 1) == "…"
    assert "truncated" in orc._truncate_utf8("x" * 100, 20)
    assert orc.handoff_slot_available({}, "implementer")
    value = state_record(tmp_path)
    value["stop_diagnostic"] = "x" * (orc.DIAGNOSTIC_LIMIT + 1)
    with pytest.raises(orc.StateFormatError):
        orc._validate_state_document({"TASK-016": value}, tmp_path / "state.json")
    with pytest.raises(SystemExit, match="4 KiB"):
        orc.resume_task_record(value, "x" * (orc.USER_REQUEST_BYTE_LIMIT + 1))
    with pytest.raises(SystemExit, match="inconsistent state"):
        orc.resume_task_record(value, "request", selected_role="other")
    value = state_record(tmp_path)
    value["processed_idle_events"] = [3]
    with pytest.raises(orc.StateFormatError):
        orc._validate_state_document({"TASK-016": value}, tmp_path / "state.json")


def test_context_truncates_required_scalar_detail_and_frame_line_bound() -> None:
    value = canonical(status=orc.UNABLE_TO_PROCEED, blockers=["b"] + ["b" * 512] * 31)
    value["summary"] = "s" * 4096
    value["requested_action"] = "r" * 4096
    context = orc.handoff_context(
        {"handoffs": [{"role": "implementer", "canonical": value}]},
        "implementer",
    )
    assert len(context.encode()) <= orc.HANDOFF_FRAME_LIMIT
    assert "truncated" in context
    with pytest.raises(ValueError, match="16 KiB"):
        orc.parse_handoff_message(
            orc.HANDOFF_PREFIX + "x" * orc.HANDOFF_FRAME_LIMIT,
            role="implementer",
        )
    non_list_blocker = canonical()
    non_list_blocker["blockers"] = "not a list"
    non_list_blocker["summary"] = "s" * 4096
    orc.handoff_context(
        {"handoffs": [{"role": "implementer", "canonical": non_list_blocker}]},
        "implementer",
    )
    short_summary = canonical()
    short_summary["summary"] = "s"
    short_summary["requested_action"] = "r" * 4096
    short_summary["files_changed"] = ["f" * 512] * 32
    short_summary["blockers"] = ["b" * 512] * 32
    orc.handoff_context(
        {"handoffs": [{"role": "implementer", "canonical": short_summary}]},
        "implementer",
    )


def test_payload_rejection_records_a_bounded_diagnostic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_file = tmp_path / "state.json"
    value = state_record(tmp_path)
    orc.save_state(state_file, {"TASK-016": value})
    monkeypatch.setenv("ORC_TASK_ID", "TASK-016")
    monkeypatch.setenv("ORC_ROLE", "implementer")
    with pytest.raises(SystemExit, match="invalid Codex"):
        orc.idle_hook(type("Args", (), {"state_file": state_file, "payload": "{bad"})())
    saved = orc.load_state(state_file)["TASK-016"]
    assert saved["handoffs"] == []
    assert saved["role_states"] == value["role_states"]
    assert saved["rejected_events"]


def test_invalid_stdin_utf8_records_a_bounded_diagnostic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_file = tmp_path / "state.json"
    orc.save_state(state_file, {"TASK-016": state_record(tmp_path)})

    class InvalidStdin:
        buffer = type("Buffer", (), {"read": lambda _self, _limit: b"\xff"})()

    monkeypatch.setattr(orc.sys, "stdin", InvalidStdin())
    monkeypatch.setenv("ORC_TASK_ID", "TASK-016")
    monkeypatch.setenv("ORC_ROLE", "implementer")
    with pytest.raises(SystemExit, match="malformed Codex"):
        orc.idle_hook(type("Args", (), {"state_file": state_file, "payload": None})())

    saved = orc.load_state(state_file)["TASK-016"]
    rejected = saved["rejected_events"][-1]
    assert "malformed Codex" in rejected["reason"]
    assert len(rejected["reason"].encode()) <= orc.DIAGNOSTIC_LIMIT


def test_stream_buffer_initialization_and_discard_until_newline() -> None:
    session = orc.ChildSession("reviewer", 1, -1, object(), strict_protocol=True)
    session.stream_rejected_diagnostics = None
    session.stream_events = None
    orc.OrcApp.read_claude_stream(session, b"x" * (orc.STREAM_EVENT_LIMIT + 1))
    assert session.stream_discarding
    orc.OrcApp.read_claude_stream(session, b"discarded\n\n")
    assert not session.stream_discarding
    assert session.stream_line_bytes == b""


def test_stream_diagnostics_cap_and_event_retention_initialization() -> None:
    session = orc.ChildSession("reviewer", 1, -1, object(), strict_protocol=True)
    for _ in range(orc.REJECTED_DIAGNOSTIC_LIMIT + 6):
        orc.OrcApp.read_claude_stream(session, b"{bad}\n")
    assert len(session.stream_rejected_diagnostics) == orc.REJECTED_DIAGNOSTIC_LIMIT
    session.stream_events = None
    orc.OrcApp.read_claude_stream(session, b'{"type":"system","session_id":"s"}\n')
    assert session.stream_events


def test_prompt_and_context_rendering_boundaries() -> None:
    assert "Rufus" in orc.reviewer_prompt({"target_directory": "target"})
    assert "COMPLETE" in orc.strict_handoff_prompt("reviewer", "token")
    with pytest.raises(ValueError, match="delivered handoff"):
        orc.handoff_context(
            {
                "handoffs": [
                    {
                        "role": "implementer",
                        "canonical": {"data": "x" * (orc.HANDOFF_FRAME_LIMIT + 1)},
                    }
                ]
            },
            "implementer",
        )
    dense = canonical(
        status=orc.UNABLE_TO_PROCEED,
        blockers=["b"] + ["b" * 512] * 31,
    )
    dense["summary"] = "s" * 4096
    dense["requested_action"] = "r" * 4096
    dense["files_changed"] = ["f" * 512] * 32
    dense["verification"] = ["v" * 512] * 32
    reduced = orc.handoff_context(
        {"handoffs": [{"role": "implementer", "canonical": dense}]},
        "implementer",
    )
    assert len(reduced.encode()) <= orc.HANDOFF_FRAME_LIMIT


@pytest.mark.integration
@pytest.mark.parametrize(
    "status,phase,stop_reason",
    [
        ("completed", "complete", "completion"),
        ("stopped", "stopped", "orchestrator_exit"),
    ],
)
def test_textual_schema_v2_ctrl_r_restarts_selected_rufus_without_reentrancy_crash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: str,
    phase: str,
    stop_reason: str,
) -> None:
    """A terminal TASK-016 can be resumed in-place by Rufus via Ctrl-R."""

    state_file = tmp_path / "state.json"
    target = tmp_path / "target"
    target.mkdir()
    marker = tmp_path / "restart.txt"
    backend = [
        sys.executable,
        "-c",
        (
            "import pathlib, time; "
            f"pathlib.Path({str(marker)!r}).write_text('reviewer'); time.sleep(2)"
        ),
    ]
    record = {
        "schema_version": orc.STATE_SCHEMA_VERSION,
        "revision": 1,
        "task_id": "TASK-016",
        "status": status,
        "phase": phase,
        "round": 2,
        "target_directory": str(target),
        "backend": "codex",
        "backend_command": backend,
        "backend_version": "test codex",
        "user_requests": ["old request"],
        "handoffs": [],
        "event_receipts": [],
        "rejected_events": [],
        "role_states": {"implementer": "inactive", "reviewer": "inactive"},
        "role_launches": {},
        "role_generations": {"implementer": 1, "reviewer": 1},
        "launch_history": [],
        "max_rounds": 5,
        "deadline_seconds": 120,
        "automatic_rounds": True,
        "deadline_at": "2099-01-01T00:00:00+00:00",
        "stop_reason": stop_reason,
        "audit_events": [],
        "audit_next_sequence": 1,
        "audit_dropped_count": 0,
        "last_terminal_event_key": None,
        "timing": {
            "task_started_at": "2025-01-01T00:00:00Z",
            "task_finished_at": "2025-01-01T00:00:00Z",
            "wall_seconds": 0,
            "agent_wall_seconds": {"implementer": 0, "reviewer": 0},
            "unattributed_wall_seconds": 0,
            "generations": [],
        },
    }
    record["last_terminal_event_key"] = orc._audit_terminal_key(
        "state_transition", None, None, status, phase, stop_reason
    )
    orc.save_state(state_file, {"TASK-016": record})
    monkeypatch.setattr(orc, "preflight_backend", lambda *_args: "test codex")

    app = orc.OrcApp(
        argparse.Namespace(state_file=state_file, codex="codex"), "TASK-016"
    )
    app.started_roles = {"implementer", "reviewer"}
    app.selected_role = "reviewer"
    app.active_role = "reviewer"
    prior_sessions: dict[str, orc.ChildSession] = {}
    prior_fds: dict[str, int] = {}
    real_close = orc.os.close
    closed_fds: list[int] = []

    def track_close(fd: int) -> None:
        closed_fds.append(fd)
        real_close(fd)

    monkeypatch.setattr(orc.os, "close", track_close)

    async def exercise() -> None:
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            # A completed/stopped task can still have the two prior terminal
            # panes registered while their children are already inactive.
            # Keep real descriptors so Ctrl-R exercises close/pop retirement,
            # rather than only launching from an empty session map.
            for role in ("implementer", "reviewer"):
                fd = os.open(os.devnull, os.O_RDWR)
                prior_fds[role] = fd
                session = orc.ChildSession(
                    role, -1, fd, app.pane(role), backend="codex"
                )
                session.exited = True
                session.retired = True
                prior_sessions[role] = session
                app.sessions[role] = session
            await pilot.press("ctrl+r")
            await pilot.pause()
            assert app.resume_prompt_active
            await pilot.press(*"resume as reviewer")
            await pilot.press("enter")
            # The launch is intentionally post-refresh; give Textual a full
            # turn to dispatch it and the child a turn to create its marker.
            await pilot.pause(0.5)
            saved = orc.load_state(state_file)["TASK-016"]
            assert saved["status"] == "active"
            assert saved["phase"] == "reviewer"
            assert saved["role_states"] == {
                "implementer": "inactive",
                "reviewer": "active",
            }
            assert marker.read_text() == "reviewer"
            assert all(session.master_fd == -1 for session in prior_sessions.values())
            assert all(fd in closed_fds for fd in prior_fds.values())
            assert all(
                prior_sessions[role] not in app.sessions.values()
                for role in prior_sessions
            )
            assert set(app.sessions) == {"reviewer"}
            assert app.sessions["reviewer"] not in prior_sessions.values()
            app.exit()

    asyncio.run(exercise())

    marker_boundary = canonical(status=orc.UNABLE_TO_PROCEED, blockers=["b" * 512] * 8)
    marker_boundary["summary"] = "s" * 1000
    marker_boundary["requested_action"] = "r" * 1000
    marker_boundary["files_changed"] = ["f" * 156] * 32
    marker_boundary["verification"] = ["v" * 156] * 32
    assert (
        len(
            orc.handoff_context(
                {"handoffs": [{"role": "implementer", "canonical": marker_boundary}]},
                "implementer",
            ).encode()
        )
        <= orc.HANDOFF_FRAME_LIMIT
    )

    short_blocker = canonical(
        token="t" * 256,
        status=orc.UNABLE_TO_PROCEED,
        blockers=["b"] + ["b" * 512] * 31,
    )
    short_blocker["summary"] = "s" * 4096
    short_blocker["requested_action"] = "r" * 4096
    assert (
        len(
            orc.handoff_context(
                {"handoffs": [{"role": "implementer", "canonical": short_blocker}]},
                "implementer",
            ).encode()
        )
        <= orc.HANDOFF_FRAME_LIMIT
    )


def test_find_task_role_and_payload_helper_fallbacks() -> None:
    state = {
        "TASK-016": {
            "implementer_id": "igor",
            "reviewer_id": "rufus",
        }
    }
    assert orc.find_task_role(state, "igor") == ("TASK-016", "implementer")
    assert orc.find_task_role(state, "rufus") == ("TASK-016", "reviewer")
    assert orc.find_task_role(state, None) == (None, None)
    assert orc.session_id_from_payload({"nested": {"id": "id"}}) == "id"
    assert (
        orc.assistant_message_from_payload({"nested": {"last_agent_message": "m"}})
        == "m"
    )


def test_git_commit_diagnostics_are_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    assert orc.current_commit(None) == "unknown"

    diagnostics: list[str] = []

    def raise_timeout(*_args: object, **_kwargs: object) -> None:
        raise orc.subprocess.TimeoutExpired("git", 1)

    monkeypatch.setattr(orc.subprocess, "run", raise_timeout)
    assert orc.current_commit(Path("."), diagnostics) == "unknown"
    assert orc.current_commit(Path(".")) == "unknown"
    assert diagnostics and "timed out" in diagnostics[0]


def test_preflight_probe_and_termination_failure_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_spawn_error(*_args: object, **_kwargs: object) -> None:
        raise OSError("spawn failed")

    monkeypatch.setattr(orc.subprocess, "Popen", raise_spawn_error)
    probe = orc._run_preflight_probe(["backend"], "version", "codex")
    assert probe.returncode is None
    assert probe.detail is not None and "spawn failed" in probe.detail

    class StubbornProcess:
        pid = 123

        def wait(self, *, timeout: float) -> None:
            raise orc.subprocess.TimeoutExpired("probe", timeout)

    def raise_kill_error(*_args: object) -> None:
        raise OSError("kill failed")

    monkeypatch.setattr(orc.os, "killpg", raise_kill_error)
    orc._terminate_preflight(StubbornProcess())  # type: ignore[arg-type]


def test_mutation_rejects_non_object_task_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(orc, "_read_state", lambda _path: {"TASK-016": "bad"})
    with pytest.raises(SystemExit, match="is not an object"):
        orc.mutate_task_state(tmp_path / "state.json", "TASK-016", lambda _record: None)
