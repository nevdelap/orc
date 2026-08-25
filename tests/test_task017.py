from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

ORC_SOURCE = Path(__file__).parents[1] / "orc"
spec = importlib.util.spec_from_loader(
    "orc_task017", SourceFileLoader("orc_task017", str(ORC_SOURCE))
)
assert spec is not None and spec.loader is not None
orc = importlib.util.module_from_spec(spec)
sys.modules["orc_task017"] = orc
spec.loader.exec_module(orc)


def record(tmp_path: Path, *, status: str = "active") -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": orc.STATE_SCHEMA_VERSION,
        "revision": 1,
        "task_id": "TASK-017",
        "status": status,
        "phase": "implementer" if status == "active" else "stopped",
        "round": 1,
        "target_directory": str(tmp_path),
        "backend": "codex",
        "backend_command": "codex",
        "user_requests": [],
        "handoffs": [],
        "event_receipts": [],
        "rejected_events": [],
        "role_states": {
            "implementer": "active" if status == "active" else "inactive",
            "reviewer": "inactive",
        },
        "role_launches": {},
        "role_generations": {"implementer": 0, "reviewer": 0},
        "max_rounds": 5,
        "deadline_seconds": 3600,
        "automatic_rounds": True,
        "deadline_at": "2099-01-01T00:00:00+00:00",
        "stop_reason": None if status == "active" else "deadline",
    }
    orc.initialize_audit_state(value, datetime(2025, 1, 1, tzinfo=UTC))
    return value


def test_audit_event_schema_and_rolling_sequence(tmp_path: Path) -> None:
    value = record(tmp_path)
    for _ in range(orc.AUDIT_EVENT_LIMIT + 4):
        orc.append_audit_event(
            value,
            "handoff_rejected",
            role="implementer",
            generation=1,
            detail="bounded diagnostic",
        )
    events = value["audit_events"]
    assert isinstance(events, list)
    assert len(events) == orc.AUDIT_EVENT_LIMIT
    assert value["audit_next_sequence"] == orc.AUDIT_EVENT_LIMIT + 5
    assert value["audit_dropped_count"] == 4
    assert [event["sequence"] for event in events] == list(
        range(5, orc.AUDIT_EVENT_LIMIT + 5)
    )
    assert all(set(event) == orc.AUDIT_EVENT_FIELDS for event in events)


def test_audit_dropped_count_saturates_and_terminal_is_idempotent(
    tmp_path: Path,
) -> None:
    value = record(tmp_path)
    value["audit_dropped_count"] = orc.AUDIT_DROPPED_LIMIT
    value["audit_events"] = [
        {
            "sequence": 1,
            "time": "2025-01-01T00:00:00Z",
            "event": "handoff_rejected",
            "role": "implementer",
            "round": 1,
            "generation": 1,
            "status_before": "active",
            "status_after": "active",
            "phase_before": "implementer",
            "phase_after": "implementer",
            "stop_reason": None,
            "commit": None,
            "detail": "rejected",
        }
    ]
    value["audit_next_sequence"] = 2
    for _ in range(orc.AUDIT_EVENT_LIMIT):
        orc.append_audit_event(
            value,
            "handoff_rejected",
            role="implementer",
            generation=1,
            detail="rejected",
        )
    assert value["audit_dropped_count"] == orc.AUDIT_DROPPED_LIMIT

    value["status"] = "stopped"
    value["phase"] = "stopped"
    value["stop_reason"] = "deadline"
    assert orc.append_audit_event(
        value,
        "cleanup",
        status_before="active",
        status_after="stopped",
        phase_before="implementer",
        phase_after="stopped",
        stop_reason="deadline",
        detail="deadline cleanup",
    )
    assert not orc.append_audit_event(
        value,
        "cleanup",
        status_before="active",
        status_after="stopped",
        phase_before="implementer",
        phase_after="stopped",
        stop_reason="deadline",
        detail="deadline cleanup",
    )


def test_schema_rejects_unsupported_and_malformed_audit(tmp_path: Path) -> None:
    value = record(tmp_path)
    missing_schema = json.loads(json.dumps(value))
    del missing_schema["schema_version"]
    with pytest.raises(orc.StateFormatError, match="unsupported pre-baseline"):
        orc._validate_state_document(
            {"TASK-017": missing_schema}, tmp_path / "state.json"
        )
    with pytest.raises(orc.StateFormatError, match="unsupported pre-baseline"):
        orc._validate_state_document(
            {"TASK-017": {**value, "schema_version": 2}},
            tmp_path / "state.json",
        )
    malformed = json.loads(json.dumps(value))
    malformed["audit_next_sequence"] = 1
    malformed["audit_events"] = [
        {
            "sequence": 2,
            "time": "2025-01-01T00:00:00Z",
            "event": "handoff_rejected",
            "role": "implementer",
            "round": 1,
            "generation": 1,
            "status_before": "active",
            "status_after": "active",
            "phase_before": "implementer",
            "phase_after": "implementer",
            "stop_reason": None,
            "commit": None,
            "detail": "bad order",
        }
    ]
    with pytest.raises(orc.StateFormatError):
        orc._validate_state_document({"TASK-017": malformed}, tmp_path / "state.json")


def test_missing_schema_is_rejected_before_mutation(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    value = record(tmp_path)
    del value["schema_version"]
    state_path.write_text(json.dumps({"TASK-017": value}, sort_keys=True))
    before = state_path.read_bytes()

    def must_not_run(_record: dict[str, object] | None) -> None:
        pytest.fail("invalid state reached mutation")

    with pytest.raises(orc.StateFormatError, match="unsupported pre-baseline"):
        orc.mutate_task_state(state_path, "TASK-017", must_not_run)
    assert state_path.read_bytes() == before


def test_generation_timing_closes_once_and_preserves_aggregate(tmp_path: Path) -> None:
    value = record(tmp_path)
    value["role_generations"] = {"implementer": 1, "reviewer": 0}
    value["role_launches"] = {"implementer": {"generation": 1, "role": "implementer"}}
    value["timing"]["generations"].append(
        {
            "role": "implementer",
            "round": 1,
            "generation": 1,
            "launched_at": "2025-01-01T00:00:00Z",
            "spawned_at": "2025-01-01T00:00:05Z",
            "ended_at": None,
            "end_event": None,
            "wall_seconds": None,
        }
    )
    end = datetime(2025, 1, 1, 0, 0, 15, tzinfo=UTC)
    assert orc._close_generation(value, "implementer", 1, "handoff_accepted", end)
    assert not orc._close_generation(value, "implementer", 1, "child_exit", end)
    generation = value["timing"]["generations"][0]
    assert generation["wall_seconds"] == 10
    assert value["timing"]["agent_wall_seconds"]["implementer"] == 10


def test_deadline_closes_open_generation_and_records_terminal_timing(
    tmp_path: Path,
) -> None:
    value = record(tmp_path)
    value["role_generations"] = {"implementer": 1, "reviewer": 0}
    value["role_launches"] = {"implementer": {"generation": 1, "role": "implementer"}}
    value["timing"]["generations"] = [
        {
            "role": "implementer",
            "round": 1,
            "generation": 1,
            "launched_at": "2025-01-01T00:00:00Z",
            "spawned_at": "2025-01-01T00:00:05Z",
            "ended_at": None,
            "end_event": None,
            "wall_seconds": None,
        }
    ]
    end = datetime(2025, 1, 1, 0, 0, 15, tzinfo=UTC)
    assert orc.transition_task(value, "deadline", now=end)
    generation = value["timing"]["generations"][0]
    assert generation["ended_at"] == "2025-01-01T00:00:15Z"
    assert generation["end_event"] == "cleanup"
    assert generation["wall_seconds"] == 10
    assert value["timing"]["agent_wall_seconds"]["implementer"] == 10
    assert value["timing"]["task_finished_at"] == "2025-01-01T00:00:15Z"
    assert value["role_launches"]["implementer"]["can_report"] is False


def test_resume_accepts_stale_terminal_launch_without_report_permission(
    tmp_path: Path,
) -> None:
    value = record(tmp_path, status="stopped")
    value["role_launches"] = {"implementer": {"generation": 1, "role": "implementer"}}

    assert orc.resume_task_record(value, "continue after the deadline") == "implementer"
    assert value["status"] == "active"
    assert value["phase"] == "implementer"


def test_terminal_and_revision_boundaries_are_rejected(tmp_path: Path) -> None:
    value = record(tmp_path, status="stopped")
    value["stop_reason"] = "deadline"
    value["last_terminal_event_key"] = None
    value["timing"]["task_finished_at"] = None
    with pytest.raises(orc.StateFormatError, match="terminal task has no terminal key"):
        orc._validate_state_document({"TASK-017": value}, tmp_path / "state.json")

    value["last_terminal_event_key"] = orc._audit_terminal_key(
        "state_transition", None, None, "stopped", "stopped", "deadline"
    )
    with pytest.raises(orc.StateFormatError, match="finished timing"):
        orc._validate_state_document({"TASK-017": value}, tmp_path / "state.json")

    value["timing"]["task_finished_at"] = "2025-01-01T00:00:00Z"
    value["revision"] = None
    with pytest.raises(orc.StateFormatError, match="invalid revision"):
        orc._validate_state_document({"TASK-017": value}, tmp_path / "state.json")


def test_handoff_and_terminal_transition_event_order(tmp_path: Path) -> None:
    value = record(tmp_path)
    value["role_generations"] = {"implementer": 1, "reviewer": 1}
    value["role_launches"] = {
        "implementer": {"generation": 1, "role": "implementer"},
        "reviewer": {"generation": 1, "role": "reviewer"},
    }
    for role, generation in (
        ("implementer", 1),
        ("reviewer", 1),
    ):
        value["timing"]["generations"].append(
            {
                "role": role,
                "round": 1,
                "generation": generation,
                "launched_at": "2025-01-01T00:00:00Z",
                "spawned_at": "2025-01-01T00:00:01Z",
                "ended_at": None,
                "end_event": None,
                "wall_seconds": None,
            }
        )
    value["role_states"] = {"implementer": "active", "reviewer": "inactive"}
    handoff = {
        "status": "HANDOFF",
        "blockers": [],
    }
    assert orc.transition_task(value, "handoff", role="implementer", handoff=handoff)
    assert [event["event"] for event in value["audit_events"]] == [
        "handoff_accepted",
        "state_transition",
    ]
    assert value["phase"] == "reviewer"
    value["role_states"] = {"implementer": "inactive", "reviewer": "active"}
    assert orc.transition_task(
        value,
        "handoff",
        role="reviewer",
        handoff={"status": "COMPLETE", "blockers": []},
    )
    assert [event["event"] for event in value["audit_events"]][-2:] == [
        "handoff_accepted",
        "state_transition",
    ]
    assert value["status"] == "completed"
    assert value["last_terminal_event_key"] is not None


def test_backward_clock_contributes_zero_and_records_diagnostic(tmp_path: Path) -> None:
    value = record(tmp_path)
    value["timing"]["task_started_at"] = "2025-01-01T00:00:10Z"
    orc._update_task_timing(value, datetime(2025, 1, 1, 0, 0, 1, tzinfo=UTC))
    assert value["timing"]["wall_seconds"] == 0
    assert value["rejected_events"][-1]["reason"] == ("backward wall-clock adjustment")


def test_audit_event_validation_rejects_boundary_shapes() -> None:
    valid = {
        "sequence": 1,
        "time": "2025-01-01T00:00:00Z",
        "event": "handoff_rejected",
        "role": "implementer",
        "round": 1,
        "generation": 1,
        "status_before": "active",
        "status_after": "active",
        "phase_before": "implementer",
        "phase_after": "implementer",
        "stop_reason": None,
        "commit": None,
        "detail": "rejected",
    }
    cases = [
        {"sequence": 0},
        {"time": "2025-01-01T00:00:00+00:00"},
        {"event": "unknown"},
        {"role": "operator"},
        {"round": 0},
        {"generation": 0},
        {"status_before": "unknown"},
        {"phase_after": "unknown"},
        {"stop_reason": "unknown"},
        {"commit": "abc"},
        {"detail": ""},
        {"event": "launch_started", "detail": "not empty"},
        {"event": "handoff_rejected", "generation": None},
        {"event": "state_transition", "status_before": None},
        {"event": "cleanup", "detail": ""},
    ]
    for change in cases:
        candidate = {**valid, **change}
        with pytest.raises(orc.StateFormatError):
            orc._validate_audit_event(candidate)
    for change in (
        {"sequence": True},
        {"time": "bad"},
        {"event": "unknown"},
        {"role": "operator"},
        {"round": False},
        {"generation": False},
        {"status_after": "unknown"},
        {"phase_before": "unknown"},
        {"stop_reason": "unknown"},
        {"detail": "x" * (orc.AUDIT_DETAIL_LIMIT + 1)},
        {"event": "state_transition", "status_before": None},
        {"event": "cleanup", "detail": ""},
    ):
        with pytest.raises(orc.StateFormatError):
            orc._validate_audit_event({**valid, **change})
    with pytest.raises(orc.StateFormatError):
        orc._validate_audit_event([])


def test_timing_and_terminal_key_validation_rejects_boundaries() -> None:
    key = orc._audit_terminal_key(
        "cleanup", None, None, "stopped", "stopped", "deadline"
    )
    with pytest.raises(orc.StateFormatError):
        orc._validate_terminal_key(key + " ")
    with pytest.raises(orc.StateFormatError):
        orc._validate_terminal_key("x" * (orc.AUDIT_TERMINAL_KEY_LIMIT + 1))
    for invalid in (
        "not-json",
        "[]",
        '["state_transition",null,null,"active","implementer",null]',
        '["state_transition","operator",null,"stopped","stopped",null]',
        '["child_exit",null,null,"stopped","stopped","child_failure"]',
        '["child_exit","implementer",1,"stopped","stopped","deadline"]',
        '["cleanup",null,null,"stopped","stopped","deadline"]',
        '["state_transition",null,1,"stopped","stopped","deadline"]',
    ):
        with pytest.raises(orc.StateFormatError):
            orc._validate_terminal_key(invalid)


def test_terminal_key_requires_current_state_and_survives_eviction(
    tmp_path: Path,
) -> None:
    value = record(tmp_path)
    key = orc._audit_terminal_key(
        "child_exit", "implementer", 1, "stopped", "stopped", "child_failure"
    )
    value["last_terminal_event_key"] = key
    with pytest.raises(orc.StateFormatError, match="terminal key"):
        orc._validate_state_document({"TASK-017": value}, tmp_path / "state.json")

    value["status"] = "stopped"
    value["phase"] = "stopped"
    value["stop_reason"] = "child_failure"
    value["timing"]["task_finished_at"] = "2025-01-01T00:00:00Z"
    orc._validate_terminal_key(key, value)
    value["audit_events"] = [
        {
            "sequence": 1,
            "time": "2025-01-01T00:00:00Z",
            "event": "child_exit",
            "role": "implementer",
            "round": 1,
            "generation": 1,
            "status_before": "active",
            "status_after": "stopped",
            "phase_before": "implementer",
            "phase_after": "stopped",
            "stop_reason": "child_failure",
            "commit": None,
            "detail": "child exited unsuccessfully",
        }
    ]
    value["audit_next_sequence"] = 2
    value["role_generations"] = {"implementer": 1, "reviewer": 0}
    for _ in range(orc.AUDIT_EVENT_LIMIT):
        orc.append_audit_event(
            value,
            "handoff_rejected",
            role="implementer",
            generation=1,
            detail="bounded rejection",
        )
    assert all(event["event"] != "child_exit" for event in value["audit_events"])
    orc._validate_state_document({"TASK-017": value}, tmp_path / "state.json")

    base = {
        "task_started_at": "2025-01-01T00:00:00Z",
        "task_finished_at": None,
        "wall_seconds": 0,
        "agent_wall_seconds": {"implementer": 0, "reviewer": 0},
        "unattributed_wall_seconds": 0,
        "generations": [],
    }
    with pytest.raises(orc.StateFormatError):
        orc._validate_timing({})
    invalid_values = [
        {"task_finished_at": "bad"},
        {"task_started_at": "bad"},
        {"wall_seconds": -1},
        {"unattributed_wall_seconds": -1},
        {"agent_wall_seconds": {"implementer": -1, "reviewer": 0}},
        {"agent_wall_seconds": {"implementer": 0}},
        {"generations": [{}]},
        {"generations": [3] * (orc.TIMING_GENERATION_LIMIT + 1)},
    ]
    for change in invalid_values:
        with pytest.raises(orc.StateFormatError):
            orc._validate_timing({**base, **change})

    generation = {
        "role": "implementer",
        "round": 1,
        "generation": 1,
        "launched_at": "2025-01-01T00:00:00Z",
        "spawned_at": "2025-01-01T00:00:01Z",
        "ended_at": None,
        "end_event": None,
        "wall_seconds": None,
    }
    for field, replacement in (
        ("role", "operator"),
        ("round", 0),
        ("launched_at", "bad"),
        ("launched_at", None),
        ("spawned_at", "bad"),
        ("spawned_at", None),
        ("end_event", "bad"),
        ("wall_seconds", -1),
    ):
        candidate = {**generation, field: replacement}
        if field == "spawned_at":
            candidate["ended_at"] = "2025-01-01T00:00:02Z"
        with pytest.raises(orc.StateFormatError):
            orc._validate_timing({**base, "generations": [candidate]})
    for change in (
        {"end_event": "child_exit"},
        {"wall_seconds": 1},
        {"ended_at": "2025-01-01T00:00:02Z", "end_event": None},
        {"ended_at": "2025-01-01T00:00:02Z", "wall_seconds": None},
    ):
        with pytest.raises(orc.StateFormatError):
            orc._validate_timing({**base, "generations": [{**generation, **change}]})
    with pytest.raises(orc.StateFormatError):
        orc._validate_timing(
            {
                **base,
                "generations": [
                    generation,
                    {**generation, "spawned_at": "2024-12-31T23:59:59Z"},
                ],
            }
        )


def test_audit_launch_events_and_open_generation_retention(tmp_path: Path) -> None:
    value = record(tmp_path)
    assert orc.append_audit_event(
        value,
        "launch_started",
        role="implementer",
        generation=1,
    )
    assert orc.append_audit_event(
        value,
        "launch_spawned",
        role="implementer",
        generation=1,
    )
    assert [event["event"] for event in value["audit_events"]] == [
        "launch_started",
        "launch_spawned",
    ]
    value["timing"]["generations"] = [
        {
            "role": "implementer",
            "round": 1,
            "generation": index + 1,
            "launched_at": "2025-01-01T00:00:00Z",
            "spawned_at": "2025-01-01T00:00:01Z",
            "ended_at": None,
            "end_event": None,
            "wall_seconds": None,
        }
        for index in range(orc.TIMING_GENERATION_LIMIT)
    ]
    assert not orc._timing_generation_slot_available(value)
    value["timing"]["generations"][0]["ended_at"] = "2025-01-01T00:00:02Z"
    assert orc._timing_generation_slot_available(value)
