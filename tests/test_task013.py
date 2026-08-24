from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

ORC_SOURCE = Path(__file__).parents[1] / "orc"
spec = importlib.util.spec_from_loader(
    "orc_task013", SourceFileLoader("orc_task013", str(ORC_SOURCE))
)
assert spec is not None and spec.loader is not None
orc = importlib.util.module_from_spec(spec)
sys.modules["orc_task013"] = orc
spec.loader.exec_module(orc)


@pytest.fixture(autouse=True)
def default_codex_preflight(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep legacy unit tests independent of an installed Codex CLI."""

    real_preflight = orc.preflight_backend

    def preflight(backend: str, command: list[str]) -> str:
        if backend == "codex" and command == ["codex"]:
            return "test codex"
        return real_preflight(backend, command)

    monkeypatch.setattr(orc, "preflight_backend", preflight)


def handoff(token: str, status: str = "HANDOFF", **extra: object) -> str:
    value: dict[str, object] = {
        "launch_token": token,
        "status": status,
        "summary": "summary",
        "files_changed": [],
        "verification": ["pytest"],
        "blockers": ["choice required"] if status == orc.UNABLE_TO_PROCEED else [],
        "requested_action": "review the result",
    }
    value.update(extra)
    return orc.HANDOFF_PREFIX + json.dumps(value, separators=(",", ":"))


def strict_record(
    target: Path, *, status: str = "active", phase: str = "implementer"
) -> dict[str, object]:
    return {
        "schema_version": orc.STATE_SCHEMA_VERSION,
        "revision": 1,
        "task_id": "TASK-013",
        "status": status,
        "phase": phase,
        "round": 1,
        "target_directory": str(target),
        "backend": "codex",
        "backend_command": "codex",
        "user_requests": [],
        "handoffs": [],
        "event_receipts": [],
        "rejected_events": [],
        "role_states": {
            "implementer": "active" if phase == "implementer" else "inactive",
            "reviewer": "active" if phase == "reviewer" else "inactive",
        },
        "role_launches": {},
        "role_generations": {"implementer": 0, "reviewer": 0},
        "max_rounds": 5,
        "deadline_seconds": 3600,
        "automatic_rounds": True,
        "deadline_at": "2099-01-01T00:00:00+00:00",
        "stop_reason": None,
    }


def test_handoff_schema_is_exact_and_bounded() -> None:
    token = "opaque"
    parsed = orc.parse_handoff_message(
        "progress\n" + handoff(token), role="implementer", launch_token=token
    )
    assert parsed["status"] == "HANDOFF"
    with pytest.raises(ValueError, match="final non-blank"):
        orc.parse_handoff_message("Status: HANDOFF", role="implementer")
    with pytest.raises(ValueError, match="only Rufus"):
        orc.parse_handoff_message(
            handoff(token, "COMPLETE"), role="implementer", launch_token=token
        )
    with pytest.raises(ValueError, match="empty blockers"):
        orc.parse_handoff_message(
            handoff(token, "COMPLETE", blockers=["bad"]),
            role="reviewer",
            launch_token=token,
        )


def test_handoff_token_and_delivered_context_bounds() -> None:
    with pytest.raises(ValueError, match="256 bytes"):
        orc.parse_handoff_message(
            handoff("x" * 257), role="implementer", launch_token="x" * 257
        )
    record = {
        "handoffs": [
            {
                "role": "implementer",
                "canonical": {
                    "launch_token": "x",
                    "status": "HANDOFF",
                    "summary": "s" * 4096,
                    "requested_action": "r" * 4096,
                    "files_changed": ["f" * 512] * 32,
                    "verification": ["v" * 512] * 32,
                    "blockers": [],
                },
            }
        ]
    }
    with pytest.raises(ValueError, match="16 KiB"):
        orc.handoff_context(record, "implementer")


def test_stale_schema_snapshot_cannot_overwrite_concurrent_update(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state.json"
    original = strict_record(tmp_path)
    orc.save_state(path, {"TASK-013": original})
    stale = orc.load_state(path)

    def pause(record: dict[str, object] | None) -> None:
        assert record is not None
        record["status"] = "paused"
        record["phase"] = "paused"
        record["stop_reason"] = "manual_pause"
        record["role_states"] = {"implementer": "inactive", "reviewer": "inactive"}

    orc.mutate_task_state(path, "TASK-013", pause)
    stale["TASK-013"]["status"] = "completed"  # type: ignore[index]
    with pytest.raises(SystemExit, match="changed concurrently"):
        orc.save_state(path, stale)
    assert orc.load_state(path)["TASK-013"]["status"] == "paused"


@pytest.mark.parametrize(
    "payload",
    [
        {"nested": {"thread-id": "t", "last-assistant-message": "x"}},
        {"thread-id": "t"},
        {"last-assistant-message": "x"},
        {"thread-id": "t", "last-assistant-message": 3},
    ],
)
def test_codex_adapter_rejects_nested_or_incomplete_payloads(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        orc.parse_codex_idle_payload(payload)


@pytest.mark.parametrize(
    "events",
    [
        [
            {"type": "system", "session_id": "s"},
            {"type": "result", "session_id": "s", "result": "x"},
        ],
        [{"type": "result", "session_id": "s", "result": "x"}],
    ],
)
def test_claude_adapter_accepts_documented_result_events(
    events: list[dict[str, object]],
) -> None:
    assert orc.parse_claude_result_event(events) == ("s", "x")


@pytest.mark.parametrize(
    "event",
    [
        {"type": "result", "result": "x"},
        {"type": "result", "session_id": "s", "result": 3},
        {"type": "result", "session_id": "s", "result": "x", "is_error": True},
        {"type": "system", "session_id": "s"},
    ],
)
def test_claude_adapter_rejects_invalid_result_events(event: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        orc.parse_claude_result_event([event])


def test_atomic_state_replacement_preserves_previous_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "state.json"
    old = {"TASK-013": strict_record(tmp_path)}
    orc.save_state(path, old)
    disk_before = orc.load_state(path)
    monkeypatch.setattr(
        orc.os, "replace", lambda *_: (_ for _ in ()).throw(OSError("stop"))
    )
    replacement = json.loads(json.dumps(disk_before))
    with pytest.raises(SystemExit, match="cannot write"):
        orc.save_state(path, replacement)
    assert orc.load_state(path) == disk_before


def test_task_mutation_serializes_and_increments_revision(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    orc.save_state(path, {"TASK-013": strict_record(tmp_path)})

    def change(record: dict[str, object] | None) -> None:
        assert record is not None
        record["status"] = "paused"
        record["phase"] = "paused"
        record["stop_reason"] = "manual_pause"
        record["role_states"] = {"implementer": "inactive", "reviewer": "inactive"}

    orc.mutate_task_state(path, "TASK-013", change)
    saved = orc.load_state(path)["TASK-013"]
    assert saved["status"] == "paused"
    assert saved["revision"] > 1


def test_mutation_rejects_invalid_revision_after_callback(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    orc.save_state(path, {"TASK-013": strict_record(tmp_path)})

    def corrupt(record: dict[str, object] | None) -> None:
        assert record is not None
        record["revision"] = True

    with pytest.raises(SystemExit, match="invalid persisted revision"):
        orc.mutate_task_state(path, "TASK-013", corrupt)


def test_legacy_resume_uses_default_limits_and_rejects_missing_blocker_reason() -> None:
    legacy = {
        "task_id": "TASK-013",
        "status": "paused",
        "phase": "paused",
        "stop_reason": "manual_pause",
        "role_states": {"implementer": "inactive", "reviewer": "inactive"},
        "user_requests": [],
        "automatic_rounds": False,
    }
    orc.resume_task_record(legacy, "continue")
    assert legacy["max_rounds"] == orc.DEFAULT_MAX_ROUNDS
    assert legacy["deadline_seconds"] == orc.DEFAULT_DEADLINE_SECONDS
    blocked = dict(legacy)
    blocked.update(
        {
            "status": "blocked",
            "phase": "blocked",
            "stop_reason": "clarification",
            "blocker_role": "implementer",
            "blocker_reason": "",
            "role_states": {"implementer": "inactive", "reviewer": "inactive"},
        }
    )
    with pytest.raises(SystemExit, match="inconsistent"):
        orc.resume_task_record(blocked, "continue")


@pytest.mark.parametrize(
    ("status", "reason", "phase"),
    [
        ("completed", "completion", "complete"),
        ("blocked", "clarification", "blocked"),
        ("paused", "manual_pause", "paused"),
        ("stopped", "deadline", "stopped"),
        ("stopped", "max_rounds", "stopped"),
    ],
)
def test_resume_matrix_starts_igor_at_round_one(
    tmp_path: Path, status: str, reason: str, phase: str
) -> None:
    record = strict_record(tmp_path, status=status, phase=phase)
    record["phase"] = phase
    record["stop_reason"] = reason
    record["role_states"] = {"implementer": "inactive", "reviewer": "inactive"}
    if status == "blocked":
        record["blocker_role"] = "implementer"
        record["blocker_reason"] = "need a decision"
    role = orc.resume_task_record(record, "continue")
    assert role == "implementer"
    assert record["status"] == "active"
    assert record["round"] == 1
    assert record["user_requests"] == ["continue"]


def test_child_failure_resume_restarts_only_failed_role(tmp_path: Path) -> None:
    record = strict_record(tmp_path, status="stopped", phase="stopped")
    record["stop_reason"] = "child_failure"
    record["role_states"] = {"implementer": "inactive", "reviewer": "failed"}
    record["child_failure"] = {"role": "reviewer"}
    record["round"] = 3
    assert orc.resume_task_record(record, "retry") == "reviewer"
    assert record["round"] == 3
    assert record["phase"] == "reviewer"


def test_inconsistent_resume_is_not_applied(tmp_path: Path) -> None:
    record = strict_record(tmp_path, status="stopped", phase="stopped")
    record["stop_reason"] = "child_failure"
    record["role_states"] = {"implementer": "failed", "reviewer": "failed"}
    record["child_failure"] = {"role": "implementer"}
    before = dict(record)
    with pytest.raises(SystemExit, match="inconsistent state"):
        orc.resume_task_record(record, "retry")
    assert record == before


@pytest.mark.parametrize(
    ("status", "reason", "phase"),
    [("completed", None, "complete"), ("paused", None, "paused")],
)
def test_resume_requires_terminal_reason(
    tmp_path: Path, status: str, reason: str | None, phase: str
) -> None:
    record = strict_record(tmp_path, status=status, phase=phase)
    record["stop_reason"] = reason
    record["role_states"] = {"implementer": "inactive", "reviewer": "inactive"}
    with pytest.raises(SystemExit, match="inconsistent state"):
        orc.resume_task_record(record, "continue")


def test_child_failure_resume_rejects_truthy_unverified_child(
    tmp_path: Path,
) -> None:
    record = strict_record(tmp_path, status="stopped", phase="stopped")
    record["stop_reason"] = "child_failure"
    record["role_states"] = {"implementer": "inactive", "reviewer": "failed"}
    record["child_failure"] = {"role": "reviewer"}
    record["live_child"] = True
    with pytest.raises(SystemExit, match="inconsistent state"):
        orc.resume_task_record(record, "retry")


def test_cli_and_in_place_resume_share_strict_matrix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    path = tmp_path / "state.json"
    record = strict_record(target, status="paused", phase="paused")
    record["stop_reason"] = "manual_pause"
    record["role_states"] = {"implementer": "inactive", "reviewer": "inactive"}
    orc.save_state(path, {"TASK-013": record})

    app = orc.OrcApp.__new__(orc.OrcApp)
    app.args = argparse.Namespace(state_file=path)
    app.task_id = "TASK-013"
    app.sessions = {}
    app.resume_prompt_active = False
    app.resume_prompt_value = ""
    app.started_roles = set()
    app._resume_prompt_widget = lambda: None
    app.update_status = lambda _message: None
    app.launch_role = lambda _role: None
    assert app.open_resume_prompt()
    assert app.submit_resume_request("continue")
    in_place = orc.load_state(path)["TASK-013"]

    cli_path = tmp_path / "state-cli.json"
    cli_record = strict_record(target, status="paused", phase="paused")
    cli_record["stop_reason"] = "manual_pause"
    cli_record["role_states"] = {
        "implementer": "inactive",
        "reviewer": "inactive",
    }
    orc.save_state(cli_path, {"TASK-013": cli_record})
    monkeypatch.setattr(orc, "run_app", lambda *_args: None)
    orc.resume(
        argparse.Namespace(state_file=cli_path, task_id="TASK-013", prompt="continue")
    )
    cli = orc.load_state(cli_path)["TASK-013"]
    for value in (in_place, cli):
        assert value["status"] == "active"
        assert value["phase"] == "implementer"
        assert value["user_requests"] == ["continue"]


def test_current_commit_timeout_reports_operation_and_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def timeout(*_args: object, **_kwargs: object) -> None:
        raise subprocess.TimeoutExpired("git", orc.SUBPROCESS_TIMEOUT_SECONDS)

    monkeypatch.setattr(orc.subprocess, "run", timeout)
    diagnostics: list[str] = []
    assert orc.current_commit(tmp_path, diagnostics) == "unknown"
    assert "git rev-parse --short HEAD" in diagnostics[0]
    assert "5 seconds" in diagnostics[0]


def test_fragmented_utf8_and_crlf_claude_stream() -> None:
    session = orc.ChildSession("reviewer", 1, -1, object(), strict_protocol=True)
    event = '{"type":"result","session_id":"s","result":"ready 🚀"}\r\n'.encode()
    split = event.index("🚀".encode()) + 1
    orc.OrcApp.read_claude_stream(session, event[:split])
    orc.OrcApp.read_claude_stream(session, event[split:])
    assert session.final_response == "ready 🚀"
    assert session.stream_error is None


def test_strict_idle_hook_correlates_token_and_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    path = tmp_path / "state.json"
    record = strict_record(target)
    record["role_launches"] = {
        "implementer": {
            "role": "implementer",
            "phase": "implementer",
            "round": 1,
            "generation": 4,
            "launch_token": "token",
            "session_id": "thread",
            "can_report": True,
        }
    }
    orc.save_state(path, {"TASK-013": record})
    monkeypatch.setenv("ORC_TASK_ID", "TASK-013")
    monkeypatch.setenv("ORC_ROLE", "implementer")
    payload = {
        "thread-id": "thread",
        "last-assistant-message": handoff("token"),
    }
    args = argparse.Namespace(state_file=path, payload=json.dumps(payload))
    monkeypatch.setattr(orc, "current_commit", lambda *_args, **_kwargs: "abc123")
    orc.idle_hook(args)
    orc.idle_hook(args)
    saved = orc.load_state(path)["TASK-013"]
    assert saved["phase"] == "reviewer"
    assert len(saved["handoffs"]) == 1
    assert len(saved["event_receipts"]) == 1
    assert saved["revision"] == 2


def test_strict_idle_rejects_context_that_exceeds_delivery_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    path = tmp_path / "state.json"
    record = strict_record(target)
    record["role_launches"] = {
        "implementer": {
            "phase": "implementer",
            "generation": 1,
            "launch_token": "token",
            "session_id": "thread",
            "can_report": True,
        }
    }
    orc.save_state(path, {"TASK-013": record})
    monkeypatch.setenv("ORC_TASK_ID", "TASK-013")
    monkeypatch.setenv("ORC_ROLE", "implementer")
    monkeypatch.setattr(orc, "current_commit", lambda *_args, **_kwargs: "abc123")
    message = handoff(
        "token",
        summary="s" * 4000,
        requested_action="r" * 4000,
        verification=["v" * 512] * 16,
    )
    assert len(message.encode()) <= orc.HANDOFF_FRAME_LIMIT
    orc.idle_hook(
        argparse.Namespace(
            state_file=path,
            payload=json.dumps(
                {"thread-id": "thread", "last-assistant-message": message}
            ),
        )
    )
    saved = orc.load_state(path)["TASK-013"]
    assert saved["phase"] == "implementer"
    assert saved["handoffs"] == []
    assert any("16 KiB" in item["reason"] for item in saved["rejected_events"])


def test_strict_idle_hook_rejects_stale_token_without_transition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    path = tmp_path / "state.json"
    record = strict_record(target)
    record["role_launches"] = {
        "implementer": {
            "phase": "implementer",
            "round": 1,
            "generation": 1,
            "launch_token": "new",
            "session_id": "thread",
            "can_report": True,
        }
    }
    orc.save_state(path, {"TASK-013": record})
    monkeypatch.setenv("ORC_TASK_ID", "TASK-013")
    monkeypatch.setenv("ORC_ROLE", "implementer")
    args = argparse.Namespace(
        state_file=path,
        payload=json.dumps(
            {"thread-id": "thread", "last-assistant-message": handoff("old")}
        ),
    )
    orc.idle_hook(args)
    saved = orc.load_state(path)["TASK-013"]
    assert saved["phase"] == "implementer"
    assert saved["handoffs"] == []
    assert saved["rejected_events"]


def test_receipt_capacity_evicts_oldest_receipt_without_growth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    path = tmp_path / "state.json"
    record = strict_record(target)
    record["role_launches"] = {
        "implementer": {
            "phase": "implementer",
            "round": 1,
            "generation": 2,
            "launch_token": "token",
            "session_id": "thread",
            "can_report": True,
        }
    }
    record["event_receipts"] = [
        {"receipt": f"old-{index}", "role": "reviewer", "generation": index}
        for index in range(1, orc.RECEIPT_LIMIT + 1)
    ]
    record["launch_history"] = [
        {"role": "reviewer", "generation": index, "can_report": False}
        for index in range(1, orc.RECEIPT_LIMIT + 1)
    ]
    orc.save_state(path, {"TASK-013": record})
    monkeypatch.setattr(orc, "current_commit", lambda *_args, **_kwargs: "abc123")
    payload = {
        "thread-id": "thread",
        "last-assistant-message": handoff("token"),
    }
    args = argparse.Namespace(state_file=path, payload=json.dumps(payload))
    orc._strict_idle_hook(
        args, payload, "TASK-013", "implementer", record, {"TASK-013": record}
    )
    assert len(record["event_receipts"]) == orc.RECEIPT_LIMIT
    assert record["event_receipts"][0]["receipt"] != "old-1"
    assert record["receipt_evictions"] == 1


def test_replay_is_detected_after_more_than_twenty_later_receipts(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    path = tmp_path / "state.json"
    record = strict_record(target)
    launch = {
        "phase": "implementer",
        "round": 1,
        "generation": 2,
        "launch_token": "token",
        "session_id": "thread",
        "can_report": True,
    }
    record["role_launches"] = {"implementer": launch}
    parsed = orc.parse_handoff_message(
        handoff("token"), role="implementer", launch_token="token"
    )
    first = {
        "task": "TASK-013",
        "role": "implementer",
        "round": 1,
        "generation": 2,
        "session_id": "thread",
        "handoff": parsed,
    }
    record["event_receipts"] = [
        {
            "receipt": orc.canonical_receipt(first),
            "role": "implementer",
            "generation": 2,
            "session_id": "thread",
        }
    ] + [
        {"receipt": f"later-{index}", "role": "reviewer", "generation": index}
        for index in range(21)
    ]
    state = {"TASK-013": record}
    payload = {"thread-id": "thread", "last-assistant-message": handoff("token")}
    args = argparse.Namespace(state_file=path, payload=json.dumps(payload))
    before = list(record["event_receipts"])
    assert orc._strict_idle_hook(
        args, payload, "TASK-013", "implementer", record, state
    )
    assert record["event_receipts"] == before
    assert record["handoffs"] == []


def test_state_and_payload_edge_contracts(tmp_path: Path) -> None:
    with pytest.raises(orc.StateFormatError):
        orc._validate_state_document([], tmp_path / "state.json")
    with pytest.raises(orc.StateFormatError):
        orc._validate_state_document({"TASK": []}, tmp_path / "state.json")
    with pytest.raises(orc.StateFormatError):
        orc._validate_state_document(
            {"TASK": {"schema_version": 99}}, tmp_path / "state.json"
        )
    with pytest.raises(orc.StateFormatError):
        orc._validate_state_document(
            {"TASK": {"revision": -1}}, tmp_path / "state.json"
        )
    invalid = strict_record(tmp_path)
    invalid["role_generations"] = {"implementer": "one", "reviewer": 0}
    with pytest.raises(orc.StateFormatError, match="role generations"):
        orc._validate_state_document({"TASK-013": invalid}, tmp_path / "state.json")
    bad = tmp_path / "bad.json"
    bad.write_text("not json")
    with pytest.raises(orc.StateFormatError):
        orc._read_state(bad)

    assert orc.payload_field([{"nested": {"status": "HANDOFF"}}], "status") == "HANDOFF"
    assert orc.message_field("Status: complete", "status") == "complete"
    assert orc.message_field("nothing", "status") is None
    assert (
        orc.handoff_status({"last-assistant-message": "status: task complete"})
        == "COMPLETE"
    )
    assert orc.handoff_status({"status": "unable-to-proceed"}) == orc.UNABLE_TO_PROCEED
    assert orc.handoff_status({"status": "ordinary"}) == "ORDINARY"


def test_schema2_validation_rejects_malformed_state_shapes(tmp_path: Path) -> None:
    def reject(change: object) -> None:
        value = strict_record(tmp_path)
        change(value)  # type: ignore[operator]
        with pytest.raises(orc.StateFormatError):
            orc._validate_state_document({"TASK-013": value}, tmp_path / "state.json")

    reject(lambda value: value.update({"task_id": "OTHER"}))
    reject(lambda value: value.update({"status": "mystery"}))
    reject(lambda value: value.update({"round": False}))
    reject(lambda value: value.update({"target_directory": ""}))
    reject(lambda value: value.update({"backend": "mystery"}))
    reject(lambda value: value.update({"backend_command": [""]}))
    reject(lambda value: value.update({"user_requests": [3]}))
    reject(lambda value: value.update({"handoffs": [3]}))
    reject(lambda value: value.update({"event_receipts": [3]}))
    reject(lambda value: value.update({"rejected_events": [3]}))
    reject(
        lambda value: value.update({"event_receipts": [{}] * (orc.RECEIPT_LIMIT + 1)})
    )
    reject(lambda value: value.update({"role_states": {}}))
    reject(
        lambda value: value.update(
            {"role_states": {"implementer": "waiting", "reviewer": "inactive"}}
        )
    )
    reject(lambda value: value.update({"role_launches": None}))
    value = strict_record(tmp_path)
    value["role_launches"] = {"implementer": {}}
    orc._validate_state_document({"TASK-013": value}, tmp_path / "state.json")
    reject(lambda value: value.update({"role_launches": {"other": {}}}))
    reject(lambda value: value.update({"role_launches": {"implementer": 3}}))
    reject(lambda value: value.update({"role_generations": {"implementer": 0}}))
    reject(
        lambda value: value.update(
            {"role_launches": {"implementer": {"phase": "other"}}}
        )
    )
    reject(
        lambda value: value.update(
            {
                "role_launches": {
                    "implementer": {
                        "phase": "implementer",
                        "generation": 1,
                        "launch_token": "",
                    }
                }
            }
        )
    )
    reject(
        lambda value: value.update(
            {
                "role_launches": {
                    "implementer": {
                        "phase": "implementer",
                        "generation": 1,
                        "launch_token": "token",
                        "can_report": "yes",
                    }
                }
            }
        )
    )
    reject(
        lambda value: value.update(
            {
                "role_launches": {
                    "implementer": {
                        "phase": "implementer",
                        "generation": 1,
                        "launch_token": "token",
                        "pid": 0,
                    }
                }
            }
        )
    )
    reject(lambda value: value.update({"launch_history": "bad"}))
    reject(lambda value: value.update({"launch_history": [{"role": "other"}]}))
    reject(lambda value: value.update({"live_child": {"role": "other", "pid": 1}}))
    reject(lambda value: value.update({"max_rounds": 0}))
    reject(lambda value: value.update({"automatic_rounds": "yes"}))
    reject(lambda value: value.update({"stop_reason": "invalid"}))
    reject(lambda value: value.update({"deadline_at": "invalid"}))


def test_receipt_generation_metadata_is_conservative(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = strict_record(tmp_path)
    history = [
        {"role": "implementer", "generation": 1, "can_report": False},
        {"role": "implementer", "generation": 2, "can_report": False},
    ]
    record["launch_history"] = history
    record["role_launches"] = {
        "implementer": {
            "phase": "implementer",
            "generation": 3,
            "launch_token": "token",
            "can_report": False,
        }
    }
    assert orc.generation_launch_record(record, "implementer", 1) is history[0]
    assert (
        orc.generation_launch_record(record, "implementer", 3)
        is record["role_launches"]["implementer"]
    )
    assert orc.generation_launch_record(record, "reviewer", 1) is None
    assert orc.generation_can_report(record, {"role": "reviewer", "generation": 1})
    assert not orc.generation_can_report(
        record, {"role": "implementer", "generation": 1}
    )
    record["role_launches"]["implementer"]["pid"] = 12  # type: ignore[index]
    monkeypatch.setattr(
        orc.os, "kill", lambda *_args: (_ for _ in ()).throw(ProcessLookupError())
    )
    assert not orc.generation_can_report(
        record, {"role": "implementer", "generation": 3}
    )
    monkeypatch.setattr(
        orc.os, "kill", lambda *_args: (_ for _ in ()).throw(OSError("unknown"))
    )
    assert orc.generation_can_report(record, {"role": "implementer", "generation": 3})
    monkeypatch.setattr(orc.os, "kill", lambda *_args: None)
    assert orc.generation_can_report(record, {"role": "implementer", "generation": 3})
    record["event_receipts"] = [
        {"role": "reviewer", "generation": 1}
    ] * orc.RECEIPT_LIMIT
    assert orc.receipt_capacity_blocked(record)
    record["event_receipts"] = []
    assert not orc.receipt_capacity_blocked(record)
    assert not orc.generation_can_report(record, {"role": 3, "generation": 1})


def test_strict_idle_repairs_legacy_receipt_container_and_records_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    record = strict_record(target)
    record["role_launches"] = {
        "implementer": {
            "phase": "implementer",
            "generation": 1,
            "launch_token": "token",
            "session_id": "thread",
            "can_report": True,
        }
    }
    record["event_receipts"] = "bad"
    record["launch_history"] = [
        {"role": "implementer", "generation": 1, "can_report": True}
    ]
    payload = {"thread-id": "thread", "last-assistant-message": handoff("token")}
    monkeypatch.setattr(orc, "current_commit", lambda *_args, **_kwargs: "abc123")
    assert orc._strict_idle_hook(
        argparse.Namespace(state_file=tmp_path / "state.json"),
        payload,
        "TASK-013",
        "implementer",
        record,
        {"TASK-013": record},
    )
    assert record["event_receipts"]
    assert record["launch_history"][0]["can_report"] is False

    record = strict_record(target)
    record["role_launches"] = {
        "implementer": {
            "phase": "implementer",
            "generation": 1,
            "launch_token": "token",
            "can_report": True,
        }
    }
    record["event_receipts"] = [3] * orc.RECEIPT_LIMIT
    assert orc._strict_idle_hook(
        argparse.Namespace(state_file=tmp_path / "state.json"),
        payload,
        "TASK-013",
        "implementer",
        record,
        {"TASK-013": record},
    )
    assert orc.handoff_reason({"blocker": "decide"}) == "decide"
    assert orc.handoff_details({"summary": "s", "nested": {"files": ["a"]}}) == {
        "summary": "s",
        "files": ["a"],
    }
    assert orc.handoff_event_key("T", "igor", object())
    assert orc.deadline_expired({"automatic_rounds": False}) is False
    assert (
        orc.workflow_active_role({"status": "paused", "phase": "implementer"}) is None
    )
    assert orc.current_round({"round": "bad"}) == 1
    assert orc.current_round({"round": 0}) == 1


def test_parser_and_transition_error_branches(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        orc._strict_json_object('{"x":1,"x":2}')
    with pytest.raises(ValueError):
        orc._strict_json_object("[]")
    for value in (None, ""):
        with pytest.raises(ValueError):
            orc._bounded_handoff_string(value, "summary")
    with pytest.raises(ValueError, match="16 KiB"):
        orc.parse_handoff_message(
            "x" * (orc.HANDOFF_FRAME_LIMIT + 1), role="implementer"
        )
    with pytest.raises(ValueError, match="schema mismatch"):
        orc.parse_handoff_message(orc.HANDOFF_PREFIX + "{}", role="implementer")
    with pytest.raises(ValueError, match="duplicate"):
        orc.parse_handoff_message(
            orc.HANDOFF_PREFIX
            + '{"launch_token":"x","status":"HANDOFF","summary":"s",'
            + '"summary":"s","files_changed":[],"verification":[],'
            + '"blockers":[],"requested_action":"r"}',
            role="implementer",
        )
    with pytest.raises(ValueError, match="invalid item"):
        orc.parse_handoff_message(
            handoff("x", files_changed=[None]), role="implementer"
        )
    with pytest.raises(ValueError, match="UNABLE"):
        orc.parse_handoff_message(
            handoff("x", orc.UNABLE_TO_PROCEED, blockers=[]), role="implementer"
        )
    with pytest.raises(ValueError, match="launch token"):
        orc.parse_handoff_message(
            handoff("old"), role="implementer", launch_token="new"
        )
    with pytest.raises(ValueError):
        orc.parse_codex_idle_payload([])
    with pytest.raises(ValueError):
        orc.parse_codex_idle_payload({"last-agent-message": "x", "thread-id": "t"})
    assert orc.parse_codex_idle_payload(
        {"last_agent_message": "x", "session_id": "t"}
    ) == ("x", "t")

    record = strict_record(tmp_path)
    assert orc.transition_task(record, "deadline")
    assert not orc.transition_task(record, "deadline")
    record = strict_record(tmp_path)
    with pytest.raises(ValueError):
        orc.transition_task(record, "child_failure", role="other")
    assert orc.transition_task(record, "child_failure", role="reviewer")
    record = strict_record(tmp_path)
    with pytest.raises(ValueError):
        orc.transition_task(record, "unknown")
    assert orc.transition_task(
        record, "handoff", role="implementer", handoff={"status": "HANDOFF"}
    )
    record = strict_record(tmp_path)
    assert orc.transition_task(
        record,
        "handoff",
        role="implementer",
        handoff={"status": orc.UNABLE_TO_PROCEED, "blockers": []},
    )
    record = strict_record(tmp_path, phase="reviewer")
    record["max_rounds"] = 2
    record["round"] = 1
    assert orc.transition_task(
        record, "handoff", role="reviewer", handoff={"status": "HANDOFF"}
    )
    assert record["round"] == 2
    record["round"] = 2
    assert orc.transition_task(
        record, "handoff", role="reviewer", handoff={"status": "HANDOFF"}
    )
    assert record["stop_reason"] == "max_rounds"
    record = strict_record(tmp_path, phase="reviewer")
    assert orc.transition_task(
        record, "handoff", role="reviewer", handoff={"status": "COMPLETE"}
    )
    with pytest.raises(ValueError):
        orc.set_stop_reason(record, "invalid")


def test_backend_and_adapter_contract_edges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for value in (None, [], [""], 3):
        with pytest.raises(SystemExit):
            orc.backend_command_value(value)
    with pytest.raises(SystemExit):
        orc.backend_from_record({})
    monkeypatch.delenv("ORC_BACKEND", raising=False)
    with pytest.raises(SystemExit):
        orc.selected_backend(argparse.Namespace(backend_selector=None))
    monkeypatch.setenv("ORC_BACKEND", "claude")
    assert orc.selected_backend(argparse.Namespace(backend_selector=None)) == "claude"
    assert orc.valid_round_limit(True) is None
    assert orc.valid_round_limit("bad") is None
    assert orc.valid_deadline_seconds(False) is None
    assert orc.valid_deadline_seconds("bad") is None
    assert (
        orc.claude_session_for_role({"claude_sessions": {"reviewer": "s"}}, "reviewer")
        == "s"
    )
    assert orc.claude_session_for_role({"reviewer_id": "r"}, "reviewer") == "r"
    assert orc.claude_session_for_role({}, "reviewer") is None
    assert orc.child_exit_code(0) == 0
    with pytest.raises(SystemExit):
        orc.backend_launch_command(
            "codex",
            ["codex"],
            "p",
            "T",
            "implementer",
            "s",
            False,
            False,
            tmp_path / "s",
        )
    with pytest.raises(SystemExit):
        orc.backend_launch_command(
            "claude",
            ["claude"],
            "p",
            "T",
            "reviewer",
            "s",
            False,
            False,
            tmp_path / "s",
        )
    codex = orc.backend_launch_command(
        "codex", ["codex"], "p", "T", "implementer", None, False, False, tmp_path / "s"
    )
    assert codex[-1].startswith("p")
    claude = orc.backend_launch_command(
        "claude", ["claude"], "p", "T", "reviewer", "s", True, False, tmp_path / "s"
    )
    assert "--resume" in claude

    with pytest.raises(ValueError):
        orc.parse_claude_result_event(
            [
                {"type": "system", "session_id": "a"},
                {"type": "system", "session_id": "b"},
            ]
        )
    with pytest.raises(ValueError):
        orc.parse_claude_result_event([{"type": "message"}])
    with pytest.raises(ValueError):
        orc.parse_claude_result_event(
            [{"type": "result", "session_id": "a", "result": "x"}], expected_session="b"
        )
    assert orc.current_commit(None) == "unknown"


def test_strict_idle_hook_rejects_protocol_edges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    path = tmp_path / "state.json"

    def invoke(record: dict[str, object], payload: object) -> bool:
        state = {"TASK-013": record}
        return orc._strict_idle_hook(
            argparse.Namespace(state_file=path),
            payload,
            "TASK-013",
            "implementer",
            record,
            state,
        )

    record = strict_record(target)
    assert not invoke(record, [])
    record = strict_record(target)
    assert not invoke(
        record, {"thread-id": "t", "last-assistant-message": handoff("x")}
    )
    record["role_launches"] = {
        "implementer": {"phase": "implementer", "launch_token": "x"}
    }
    assert not invoke(record, {"thread-id": "t", "last-assistant-message": "bad"})
    record = strict_record(target, status="completed", phase="complete")
    record["stop_reason"] = "completion"
    record["role_launches"] = {
        "implementer": {"phase": "implementer", "launch_token": "x"}
    }
    assert invoke(record, {"thread-id": "t", "last-assistant-message": handoff("x")})
    record = strict_record(target)
    record["role_launches"] = {
        "implementer": {"phase": "reviewer", "launch_token": "x"}
    }
    assert not invoke(
        record, {"thread-id": "t", "last-assistant-message": handoff("x")}
    )
    record = strict_record(target)
    record["role_launches"] = {
        "implementer": {
            "phase": "implementer",
            "launch_token": "x",
            "session_id": "expected",
        }
    }
    assert not invoke(
        record, {"thread-id": "other", "last-assistant-message": handoff("x")}
    )
    record = strict_record(target)
    record["role_launches"] = {
        "implementer": {
            "phase": "implementer",
            "launch_token": "x",
            "generation": 1,
            "can_report": True,
        }
    }
    record["event_receipts"] = [
        {"receipt": f"r-{i}", "role": "implementer", "generation": 1}
        for i in range(orc.RECEIPT_LIMIT)
    ]
    monkeypatch.setattr(orc, "current_commit", lambda *_args, **_kwargs: "abc")
    assert not invoke(
        record, {"thread-id": "t", "last-assistant-message": handoff("x")}
    )
    assert record["stop_reason"] == "child_failure"
    record = strict_record(target)
    record["role_launches"] = {
        "implementer": {"phase": "implementer", "launch_token": "x"}
    }
    record.pop("target_directory")
    assert not invoke(
        record, {"thread-id": "t", "last-assistant-message": handoff("x")}
    )


def test_strict_launch_persists_current_generation_and_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    path = tmp_path / "state.json"
    record = strict_record(target)
    record["user_requests"] = ["implement"]
    record["backend_command"] = "codex"
    orc.save_state(path, {"TASK-013": record})
    app = orc.OrcApp(argparse.Namespace(state_file=path), "TASK-013")
    master, slave = os.openpty()

    class Pane:
        def show_message(self, _message: str) -> None:
            pass

    monkeypatch.setattr(app, "fork_codex", lambda *_args, **_kwargs: (12345, master))
    monkeypatch.setattr(app, "pane", lambda _role: Pane())
    monkeypatch.setattr(app, "update_layout", lambda: None)
    monkeypatch.setattr(app, "set_master_reader", lambda _session: None)
    monkeypatch.setattr(app, "resize_session", lambda _session: None)
    monkeypatch.setattr(app, "schedule_resize", lambda: None)
    monkeypatch.setattr(app, "refresh_status", lambda: None)
    try:
        app.launch_role("implementer")
        saved = orc.load_state(path)["TASK-013"]
        launch = saved["role_launches"]["implementer"]
        assert launch["generation"] == 1
        assert launch["pid"] == 12345
        assert saved["live_child"] == {"role": "implementer", "pid": 12345}
        assert saved["launch_backend"] == "codex"
        assert app.sessions["implementer"].strict_protocol
    finally:
        os.close(slave)
        os.close(master)


def test_strict_claude_exit_persists_session_before_idle_transition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    path = tmp_path / "state-1.json"
    record = strict_record(target, phase="reviewer")
    record["role_states"] = {"implementer": "inactive", "reviewer": "active"}
    record["role_launches"] = {
        "reviewer": {
            "phase": "reviewer",
            "round": 1,
            "generation": 1,
            "launch_token": "token",
            "session_id": "thread",
            "can_report": True,
        }
    }
    orc.save_state(path, {"TASK-013": record})
    app = orc.OrcApp(argparse.Namespace(state_file=path), "TASK-013")
    app.update_status = lambda _message: None
    app.refresh_workflow_ui = lambda: None
    monkeypatch.setattr(orc, "current_commit", lambda *_args, **_kwargs: "abc123")
    response = handoff("token")
    session = orc.ChildSession(
        "reviewer", 1, -1, object(), backend="claude", strict_protocol=True
    )
    session.session_id = "thread"
    session.launch_token = "token"
    session.stream_events = [
        {"type": "result", "session_id": "thread", "result": response}
    ]
    assert app.handle_claude_exit(session, {"TASK-013": record}, record, 0)
    saved = orc.load_state(path)["TASK-013"]
    assert saved["claude_sessions"]["reviewer"] == "thread"
    assert saved["phase"] == "implementer"


def test_in_place_resume_validates_target_and_backend(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    app = orc.OrcApp.__new__(orc.OrcApp)
    app.sessions = {}
    paused = strict_record(target, status="paused", phase="paused")
    paused["stop_reason"] = "manual_pause"
    paused["role_states"] = {"implementer": "inactive", "reviewer": "inactive"}
    assert app.can_resume_in_place(paused)
    target.rmdir()
    assert not app.can_resume_in_place(paused)
    target.mkdir()
    paused["backend"] = "invalid"
    assert not app.can_resume_in_place(paused)


def test_launch_boundary_stops_when_all_receipts_are_still_reportable(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    path = tmp_path / "state.json"
    record = strict_record(target)
    record["user_requests"] = ["implement"]
    record["role_launches"] = {
        "implementer": {
            "phase": "implementer",
            "generation": 2,
            "launch_token": "current",
            "can_report": True,
        }
    }
    record["launch_history"] = [
        {"role": "implementer", "generation": index, "can_report": True}
        for index in range(1, orc.RECEIPT_LIMIT + 1)
    ]
    record["event_receipts"] = [
        {"receipt": str(index), "role": "implementer", "generation": index}
        for index in range(1, orc.RECEIPT_LIMIT + 1)
    ]
    orc.save_state(path, {"TASK-013": record})
    app = orc.OrcApp(argparse.Namespace(state_file=path), "TASK-013")
    app.update_status = lambda _message: None
    app.refresh_workflow_ui = lambda: None
    app.launch_role("implementer")
    saved = orc.load_state(path)["TASK-013"]
    assert saved["status"] == "stopped"
    assert saved["stop_reason"] == "child_failure"
    assert saved["child_failure"]["reason"].startswith("receipt_capacity")


def test_claude_strict_stream_and_handoff_error_matrix() -> None:
    session = orc.ChildSession("reviewer", 1, -1, object(), strict_protocol=True)
    events = (
        b'{"type":"system","session_id":"s"}\r\n'
        b'{"type":"result","session_id":"s","result":"ok"}\r\n'
    )
    orc.OrcApp.read_claude_stream(session, events)
    assert session.session_id == "s"
    assert orc.OrcApp.claude_handoff(session) is None
    session.launch_token = "token"
    session.stream_events = [
        {
            "type": "result",
            "session_id": "s",
            "result": handoff("token"),
        }
    ]
    session.final_response = handoff("token")
    assert orc.OrcApp.claude_handoff(session) is not None
    for event in (
        {"type": "system"},
        {"type": "system", "session_id": "a"},
        {"type": "system", "session_id": "b"},
        {"type": "result", "is_error": True, "session_id": "a", "result": "x"},
        {"type": "result", "session_id": "a"},
        {"type": "result", "session_id": "a", "result": ""},
        {"type": "result", "session_id": "b", "result": "x"},
        {"type": "other"},
        [],
    ):
        value = json.dumps(event).encode() + b"\n"
        orc.OrcApp.read_claude_stream(session, value)
    legacy = orc.ChildSession("reviewer", 1, -1, object())
    legacy.stream_events = [
        {"type": "result", "session_id": "s", "result": "status: HANDOFF"}
    ]
    assert orc.OrcApp.claude_handoff(legacy) is not None
    assert (
        orc.OrcApp.claude_handoff(orc.ChildSession("reviewer", 1, -1, object())) is None
    )


def test_child_failure_and_persisted_child_liveness_edges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    path = tmp_path / "state.json"
    record = strict_record(target)
    orc.save_state(path, {"TASK-013": record})
    app = orc.OrcApp(argparse.Namespace(state_file=path), "TASK-013")
    app.update_status = lambda _message: None
    app.refresh_workflow_ui = lambda: None
    app.record_child_failure("implementer", "failed")
    assert orc.load_state(path)["TASK-013"]["stop_reason"] == "child_failure"
    assert orc.persisted_child_live({}) is False
    assert orc.persisted_child_live({"live_child": False}) is False
    assert orc.persisted_child_live({"live_child": True}) is True
    assert orc.persisted_child_live({"live_child": {"pid": "bad"}}) is True
    monkeypatch.setattr(
        orc.os, "kill", lambda *_args: (_ for _ in ()).throw(ProcessLookupError())
    )
    assert orc.persisted_child_live({"live_child": {"pid": 12}}) is False
    monkeypatch.setattr(
        orc.os, "kill", lambda *_args: (_ for _ in ()).throw(PermissionError())
    )
    assert orc.persisted_child_live({"live_child": {"pid": 12}}) is True
    monkeypatch.setattr(
        orc.os, "kill", lambda *_args: (_ for _ in ()).throw(OSError("unknown"))
    )
    assert orc.persisted_child_live({"live_child": {"pid": 12}}) is True
    monkeypatch.setattr(orc.os, "kill", lambda *_args: None)
    assert orc.persisted_child_live({"live_child": {"pid": 12}}) is True
    assert (
        orc.persisted_role_state(
            {"role_states": {"implementer": "waiting"}}, "implementer"
        )
        == "waiting"
    )


def test_strict_idle_git_timeout_stops_without_false_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    path = tmp_path / "state.json"
    record = strict_record(target)
    record["role_launches"] = {
        "implementer": {
            "phase": "implementer",
            "generation": 1,
            "launch_token": "token",
            "session_id": "thread",
            "can_report": True,
        }
    }
    state = {"TASK-013": record}
    payload = {"thread-id": "thread", "last-assistant-message": handoff("token")}

    def timeout(_cwd: object, diagnostics: list[str] | None = None) -> str:
        assert diagnostics is not None
        diagnostics.append("git rev-parse --short HEAD timed out after 5 seconds")
        return "unknown"

    monkeypatch.setattr(orc, "current_commit", timeout)
    assert not orc._strict_idle_hook(
        argparse.Namespace(state_file=path),
        payload,
        "TASK-013",
        "implementer",
        record,
        state,
    )
    assert record["child_failure"]["operation"] == "git rev-parse --short HEAD"
    assert record["child_failure"]["elapsed_limit_seconds"] == 5
    assert record["handoffs"] == []


def test_resume_validation_rejects_every_inconsistent_metadata_shape(
    tmp_path: Path,
) -> None:
    with pytest.raises(SystemExit, match="non-empty"):
        orc.resume_task_record(
            strict_record(tmp_path, status="paused", phase="paused"), " "
        )
    active = strict_record(tmp_path)
    with pytest.raises(SystemExit, match="already active"):
        orc.resume_task_record(active, "continue")
    unknown = strict_record(tmp_path, status="mystery", phase="stopped")
    with pytest.raises(SystemExit, match="inconsistent"):
        orc.resume_task_record(unknown, "continue")
    for mutation in (
        lambda value: value.update(
            {"role_states": {"implementer": "active", "reviewer": "inactive"}}
        ),
        lambda value: value.update(
            {"role_launches": {"implementer": {"can_report": True}}}
        ),
        lambda value: value.update({"user_requests": [3]}),
        lambda value: value.update({"max_rounds": 99}),
        lambda value: value.update({"deadline_seconds": 1}),
    ):
        value = strict_record(tmp_path, status="paused", phase="paused")
        value["stop_reason"] = "manual_pause"
        value["role_states"] = {"implementer": "inactive", "reviewer": "inactive"}
        mutation(value)
        with pytest.raises(SystemExit, match="inconsistent"):
            orc.resume_task_record(value, "continue")


def test_claude_exit_strict_failure_and_idle_error_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    path = tmp_path / "state-1.json"
    record = strict_record(target, phase="reviewer")
    record["role_states"] = {"implementer": "inactive", "reviewer": "active"}
    orc.save_state(path, {"TASK-013": record})
    app = orc.OrcApp(argparse.Namespace(state_file=path), "TASK-013")
    app.update_status = lambda _message: None
    app.refresh_workflow_ui = lambda: None
    failed = orc.ChildSession(
        "reviewer", 1, -1, object(), backend="claude", strict_protocol=True
    )
    assert app.handle_claude_exit(failed, {"TASK-013": record}, record, 1)
    assert orc.load_state(path)["TASK-013"]["stop_reason"] == "child_failure"

    path = tmp_path / "state-2.json"
    app.args.state_file = path
    record = strict_record(target, phase="reviewer")
    record["role_states"] = {"implementer": "inactive", "reviewer": "active"}
    orc.save_state(path, {"TASK-013": record})
    invalid = orc.ChildSession(
        "reviewer", 1, -1, object(), backend="claude", strict_protocol=True
    )
    invalid.stream_error = "bad stream"
    assert app.handle_claude_exit(invalid, {"TASK-013": record}, record, 0)
    assert orc.load_state(path)["TASK-013"]["stop_reason"] == "child_failure"

    path = tmp_path / "state-3.json"
    app.args.state_file = path
    record = strict_record(target, phase="reviewer")
    record["role_states"] = {"implementer": "inactive", "reviewer": "active"}
    record["role_launches"] = {
        "reviewer": {
            "phase": "reviewer",
            "generation": 1,
            "launch_token": "token",
            "session_id": "thread",
            "can_report": True,
        }
    }
    orc.save_state(path, {"TASK-013": record})
    session = orc.ChildSession(
        "reviewer", 1, -1, object(), backend="claude", strict_protocol=True
    )
    session.session_id = "thread"
    session.launch_token = "token"
    session.stream_events = [
        {"type": "result", "session_id": "thread", "result": handoff("token")}
    ]
    monkeypatch.setattr(
        orc, "idle_hook", lambda _args: (_ for _ in ()).throw(SystemExit("idle failed"))
    )
    assert app.handle_claude_exit(session, {"TASK-013": record}, record, 0)
    assert orc.load_state(path)["TASK-013"]["stop_reason"] == "child_failure"


def test_strict_launch_rejects_invalid_preconditions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    app = orc.OrcApp(argparse.Namespace(state_file=tmp_path / "state.json"), "TASK-013")
    app.update_status = lambda _message: None
    app.refresh_workflow_ui = lambda: None
    record = strict_record(target)
    record["user_requests"] = []
    record["implementer_id"] = "thread"
    record["automatic_rounds"] = False
    path = tmp_path / "launch-valid.json"
    app.args.state_file = path
    orc.save_state(path, {"TASK-013": record})
    app.launch_role("implementer")
    saved = orc.load_state(path)["TASK-013"]
    assert saved["status"] == "stopped"
    assert saved["stop_reason"] == "child_failure"
    assert saved["child_failure"]["role"] == "implementer"

    for index, mutate in enumerate(
        (
            lambda value: value.pop("target_directory"),
            lambda value: value.update({"backend": "invalid"}),
            lambda value: value.update({"user_requests": "invalid"}),
        )
    ):
        path = tmp_path / f"launch-{index}.json"
        app.args.state_file = path
        record = strict_record(target)
        mutate(record)
        path.write_text(json.dumps({"TASK-013": record}))
        with pytest.raises(SystemExit, match="invalid|missing required"):
            app.launch_role("implementer")


def test_legacy_idle_hook_terminal_and_replay_matrix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    monkeypatch.setattr(orc, "current_commit", lambda *_args, **_kwargs: "abc123")
    monkeypatch.setenv("ORC_TASK_ID", "TASK-013")

    def run(
        record: dict[str, object], role: str, message: str, name: str
    ) -> dict[str, object]:
        path = tmp_path / f"{name}.json"
        orc.save_state(path, {"TASK-013": record})
        monkeypatch.setenv("ORC_ROLE", role)
        orc.idle_hook(
            argparse.Namespace(
                state_file=path,
                payload=json.dumps(
                    {"thread-id": "thread", "last-assistant-message": message}
                ),
            )
        )
        return orc.load_state(path)["TASK-013"]

    base = {
        "status": "active",
        "phase": "implementer",
        "round": 0,
        "target_directory": str(target),
        "handoffs": [],
        "processed_idle_events": [],
        "role_generations": {},
        "max_rounds": 2,
        "automatic_rounds": False,
        "implementer_id": None,
        "reviewer_id": None,
    }
    saved = run(dict(base), "implementer", "status: HANDOFF", "legacy-implementer")
    assert saved["phase"] == "reviewer"
    saved = run(
        {**base, "phase": "reviewer"}, "reviewer", "status: COMPLETE", "legacy-complete"
    )
    assert saved["status"] == "completed"
    saved = run(
        {**base, "phase": "implementer"},
        "implementer",
        "status: UNABLE_TO_PROCEED\nreason: choose a version",
        "legacy-blocked",
    )
    assert saved["status"] == "blocked"
    duplicate = dict(base)
    duplicate["processed_idle_events"] = [
        orc.handoff_event_key(
            "TASK-013",
            "implementer",
            {"thread-id": "thread", "last-assistant-message": "status: HANDOFF"},
        )
    ]
    saved = run(duplicate, "implementer", "status: HANDOFF", "legacy-duplicate")
    assert saved["handoffs"] == []
    mismatch = {**base, "phase": "reviewer"}
    saved = run(mismatch, "implementer", "status: HANDOFF", "legacy-mismatch")
    assert saved["handoffs"] == []
    paused = {**base, "status": "paused"}
    saved = run(paused, "reviewer", "status: HANDOFF", "legacy-paused")
    assert saved["handoffs"] == []


def test_state_lock_and_ui_edge_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "state.json"
    original_mkdir = Path.mkdir

    def fail_mkdir(self: Path, *args: object, **kwargs: object) -> None:
        if self == path.parent:
            raise OSError("mkdir failed")
        original_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", fail_mkdir)
    with pytest.raises(SystemExit, match="cannot write"):
        with orc.state_lock(path):
            pass
    monkeypatch.undo()

    monkeypatch.setattr(
        Path,
        "open",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("open failed")),
    )
    with pytest.raises(SystemExit, match="cannot lock"):
        with orc.state_lock(path):
            pass
    monkeypatch.undo()

    app = orc.OrcApp(argparse.Namespace(state_file=path), "TASK-013")
    app.sessions = {}
    assert app._handoffs_for_role({"handoffs": "bad"}, "implementer") == []
    assert (
        app.role_state({"status": "active", "phase": "other"}, "implementer")
        == "not started"
    )
    assert (
        app.role_state(
            {"status": "paused", "handoffs": [{"role": "reviewer"}]}, "reviewer"
        )
        == "waiting"
    )
    session = orc.ChildSession("reviewer", 1, -1, object())
    app.sessions["reviewer"] = session
    assert (
        app.role_state(
            {
                "status": "active",
                "phase": "implementer",
                "handoffs": [{"role": "reviewer"}],
            },
            "reviewer",
        )
        == "waiting"
    )
    assert orc.persisted_role_state({}, "implementer") == "inactive"
    assert (
        orc.persisted_role_state(
            {"child_failure": {"role": "implementer"}}, "implementer"
        )
        == "failed"
    )
    assert (
        orc.persisted_role_state({"status": "active", "phase": "reviewer"}, "reviewer")
        == "active"
    )
    assert orc.OrcApp._status_text("plain", "red").plain == "plain"
    assert app._visible_status_keys(
        {"task": "t", "igor": "i", "rufus": "r", "backend": "b", "hint": "h"},
        200,
    )[0] == {"task", "igor", "rufus", "backend", "hint"}
    app.scroll_target = "unknown"
    app.pane = lambda role: role
    assert app.scroll_pane() == "implementer"
    app.cycle_scroll_target()
    assert app.scroll_target == "reviewer"


def test_session_cleanup_io_and_size_edge_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    path = tmp_path / "state.json"
    record = strict_record(target)
    orc.save_state(path, {"TASK-013": record})
    app = orc.OrcApp(argparse.Namespace(state_file=path), "TASK-013")
    app.update_status = lambda _message: None
    app.refresh_status = lambda: None
    app.close_master_reader = lambda _session: None
    app.drain_session = lambda _session: None
    app.read_claude_stream = lambda *_args: None

    class Pane:
        def feed(self, _data: bytes) -> None:
            pass

        def scroll_to_end(self) -> None:
            pass

    session = orc.ChildSession("implementer", 1, 4, Pane())
    monkeypatch.setattr(orc.os, "read", lambda *_args: b"output")
    app.read_session(session)
    session.backend = "claude"
    app.read_session(session)
    monkeypatch.setattr(orc.os, "read", lambda *_args: b"")
    app.read_session(session)
    monkeypatch.setattr(
        orc.os, "read", lambda *_args: (_ for _ in ()).throw(OSError(5, "io"))
    )
    app.read_session(session)
    app.sessions["implementer"] = session
    app.write_active(b"x")

    retired = orc.ChildSession("reviewer", 2, -1, Pane())
    app.sessions["reviewer"] = retired
    monkeypatch.setattr(
        orc.os,
        "killpg",
        lambda *_args: (_ for _ in ()).throw(ProcessLookupError()),
    )
    monkeypatch.setattr(
        app,
        "_wait_for_retirement",
        lambda item, _limit: setattr(item, "exited", True),
    )
    app.retire_session(retired)
    app.retire_session(retired)
    assert retired in app.retired_sessions

    class Size:
        width = 10
        height = 4

    class Gutter:
        left = right = top = bottom = 1

    class StyledPane:
        content_size = None
        size = Size()
        styles = type("Styles", (), {"gutter": Gutter()})()

    assert orc.OrcApp.pane_terminal_size(StyledPane()) == (8, 2)
    StyledPane.styles.gutter = None
    assert orc.OrcApp.pane_terminal_size(StyledPane()) == (8, 2)
    assert orc.OrcApp.pane_terminal_size(type("Empty", (), {})()) == (2, 2)


def test_state_defensive_cleanup_and_diagnostic_edges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "state.json"
    monkeypatch.setattr(orc.os, "name", "nt")
    with orc.state_lock(path):
        pass
    monkeypatch.setattr(
        orc.os,
        "replace",
        lambda *_args: (_ for _ in ()).throw(OSError("replace")),
    )
    monkeypatch.setattr(
        orc.os,
        "unlink",
        lambda *_args: (_ for _ in ()).throw(OSError("unlink")),
    )
    with pytest.raises(SystemExit, match="cannot write"):
        orc._atomic_write_state(path, {})
    monkeypatch.undo()
    with pytest.raises(SystemExit, match="unknown task"):
        orc.mutate_task_state(path, "missing", lambda _record: None)
    assert (
        orc.mutate_task_state(path, "missing", lambda _record: None, create=True)
        is None
    )
    monkeypatch.setattr(
        orc.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            subprocess.CalledProcessError(1, "git")
        ),
    )
    diagnostics: list[str] = []
    assert orc.current_commit(tmp_path, diagnostics) == "unknown"
    assert diagnostics
    assert (
        orc.latest_canonical_handoff(
            {"handoffs": [{"role": "reviewer", "schema_version": 1}]}, "reviewer"
        )
        is not None
    )
    assert orc.handoff_context({"handoffs": "bad"}, "reviewer").startswith(
        "No validated"
    )


def test_remaining_parser_bounds_and_timestamp_edges() -> None:
    assert orc.parse_timestamp("2026-01-01T00:00:00") is not None
    assert orc.parse_timestamp("not-a-time") is None
    assert orc.parse_timestamp(None) is None
    with pytest.raises(ValueError):
        orc.parse_handoff_message(3, role="implementer")  # type: ignore[arg-type]
    value = json.loads(handoff("x").removeprefix(orc.HANDOFF_PREFIX))
    value.pop("status")
    with pytest.raises(ValueError, match="missing"):
        orc.parse_handoff_message(
            orc.HANDOFF_PREFIX + json.dumps(value), role="implementer"
        )
    value = json.loads(handoff("x").removeprefix(orc.HANDOFF_PREFIX))
    value["unknown"] = True
    with pytest.raises(ValueError, match="unknown"):
        orc.parse_handoff_message(
            orc.HANDOFF_PREFIX + json.dumps(value), role="implementer"
        )
    with pytest.raises(ValueError, match="not allowed"):
        orc.parse_handoff_message(handoff("x", status="OTHER"), role="implementer")
    with pytest.raises(ValueError, match="at most 32"):
        orc.parse_handoff_message(
            handoff("x", verification=["x"] * 33), role="implementer"
        )
    with pytest.raises(ValueError, match="512"):
        orc.parse_handoff_message(
            handoff("x", files_changed=["x" * 513]), role="implementer"
        )
    wrong_role = {"handoffs": [{"role": "reviewer"}, {"role": "implementer"}]}
    assert orc.latest_canonical_handoff(wrong_role, "reviewer") is None
    small = {"handoffs": [{"role": "reviewer", "canonical": {"status": "HANDOFF"}}]}
    assert "status" in orc.handoff_context(small, "reviewer")
    record: dict[str, object] = {"rejected_events": "bad"}
    orc.record_rejected_event(record, "x" * (orc.DIAGNOSTIC_LIMIT + 1))
    assert isinstance(record["rejected_events"], list)
    assert orc.launch_record({"role_launches": []}, "implementer") is None
    assert (
        orc.persisted_role_state(
            {"schema_version": orc.STATE_SCHEMA_VERSION, "role_states": {}},
            "implementer",
        )
        == "inactive"
    )
