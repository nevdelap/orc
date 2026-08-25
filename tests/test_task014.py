from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

ORC_SOURCE = Path(__file__).parents[1] / "orc"
spec = importlib.util.spec_from_loader(
    "orc_task014", SourceFileLoader("orc_task014", str(ORC_SOURCE))
)
assert spec is not None and spec.loader is not None
orc = importlib.util.module_from_spec(spec)
sys.modules["orc_task014"] = orc
spec.loader.exec_module(orc)


FAKE_BACKEND = r"""#!/usr/bin/env python3
import json
import os
import sys
import time

mode = os.environ.get("FAKE_MODE", "compatible")
calls_file = os.environ.get("FAKE_CALLS")
if calls_file:
    with open(calls_file, "a", encoding="utf-8") as stream:
        stream.write(json.dumps(sys.argv[1:]) + "\n")

if sys.argv[1:] == ["--version"]:
    if mode == "missing-version":
        raise SystemExit(0)
    if mode == "nonzero":
        print("probe failed", file=sys.stderr)
        raise SystemExit(7)
    if mode == "timeout":
        time.sleep(2)
        raise SystemExit(0)
    if mode == "long-version":
        print("v" + "x" * 200)
    elif mode == "invalid-version":
        sys.stdout.buffer.write(b"v1.2.3\xff\n")
    else:
        print("fake-backend 1.2.3")
    raise SystemExit(0)

if sys.argv[1:] == ["--help"]:
    if mode == "claude-missing-help":
        print("Usage: backend")
    elif mode == "help-overflow":
        print("x" * 65537)
    else:
        print("--print --output-format stream-json --input-format text --resume")
    raise SystemExit(0)

if sys.argv[1:] == ["resume", "--help"]:
    if mode == "codex-missing-resume":
        print("Usage: codex resume")
    elif mode == "resume-overflow":
        print("x" * 65537)
    else:
        print("resume -c --config SESSION_ID PROMPT")
    raise SystemExit(0)

raise SystemExit(0)
"""


def fake_backend(tmp_path: Path, *, mode: str = "compatible") -> tuple[Path, Path]:
    executable = tmp_path / "fake backend executable"
    executable.write_text(FAKE_BACKEND)
    executable.chmod(0o755)
    calls = tmp_path / "calls.jsonl"
    return executable, calls


def strict_record(target: Path, backend: str, command: Path) -> dict[str, object]:
    return {
        "schema_version": orc.STATE_SCHEMA_VERSION,
        "revision": 1,
        "task_id": "TASK-014",
        "status": "paused",
        "phase": "paused",
        "round": 2,
        "target_directory": str(target.resolve()),
        "backend": backend,
        "backend_command": str(command),
        "backend_version": "fake-backend 1.2.3",
        "user_requests": ["old request"],
        "handoffs": [],
        "event_receipts": [],
        "rejected_events": [],
        "role_states": {"implementer": "inactive", "reviewer": "inactive"},
        "role_launches": {},
        "role_generations": {"implementer": 0, "reviewer": 0},
        "max_rounds": 5,
        "deadline_seconds": 3600,
        "automatic_rounds": True,
        "deadline_at": "2099-01-01T00:00:00+00:00",
        "stop_reason": "manual_pause",
        "audit_events": [],
        "audit_next_sequence": 1,
        "audit_dropped_count": 0,
        "last_terminal_event_key": orc._audit_terminal_key(
            "state_transition",
            None,
            None,
            "paused",
            "paused",
            "manual_pause",
        ),
        "timing": {
            "task_started_at": "2025-01-01T00:00:00Z",
            "task_finished_at": "2025-01-01T00:00:00Z",
            "wall_seconds": 0,
            "agent_wall_seconds": {"implementer": 0, "reviewer": 0},
            "unattributed_wall_seconds": 0,
            "generations": [],
        },
    }


def test_codex_preflight_uses_exact_argv_and_records_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable, calls = fake_backend(tmp_path)
    monkeypatch.setenv("FAKE_CALLS", str(calls))

    assert orc.probe_codex([str(executable)]) == "fake-backend 1.2.3"
    assert [json.loads(line) for line in calls.read_text().splitlines()] == [
        ["--version"],
        ["--help"],
        ["resume", "--help"],
    ]


def test_claude_preflight_uses_exact_argv_and_rejects_missing_capability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable, calls = fake_backend(tmp_path)
    monkeypatch.setenv("FAKE_CALLS", str(calls))
    assert orc.probe_claude([str(executable)]) == "fake-backend 1.2.3"
    assert [json.loads(line) for line in calls.read_text().splitlines()] == [
        ["--version"],
        ["--help"],
    ]

    monkeypatch.setenv("FAKE_MODE", "claude-missing-help")
    with pytest.raises(SystemExit, match="backend claude executable.*--help missing"):
        orc.probe_claude([str(executable)])


def test_malformed_executable_argv_has_bounded_backend_diagnostic() -> None:
    with pytest.raises(
        SystemExit,
        match=r"backend codex executable.*failed version: embedded null byte",
    ):
        orc.probe_codex(["bad\x00command"])


def test_help_capabilities_require_literal_tokens() -> None:
    claude_missing = orc._required_help_tokens(
        "--printish --output-formatters stream-jsonx --input-format "
        "textish --resumeable",
        orc.CLAUDE_REQUIRED_HELP,
    )
    assert claude_missing == [
        "--print",
        "--output-format",
        "stream-json",
        "text",
        "--resume",
    ]
    codex_missing = orc._required_help_tokens(
        "resumable --configurator SESSION_ID_SUFFIX PROMPTING",
        orc.CODEX_REQUIRED_RESUME_HELP,
    )
    assert codex_missing == [
        "resume",
        "-c or --config",
        "SESSION_ID or [SESSION_ID]",
        "PROMPT or [PROMPT]",
    ]


@pytest.mark.parametrize(
    ("builder", "flag"),
    [
        (orc.add_agentbox_codex_flag, orc.CODEX_AGENTBOX_FLAG),
        (orc.add_agentbox_claude_flag, orc.CLAUDE_AGENTBOX_FLAG),
    ],
)
def test_agentbox_flag_is_deduplicated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    builder: object,
    flag: str,
) -> None:
    marker = tmp_path / "identity"
    marker.write_text("")
    monkeypatch.setattr(orc, "AGENTBOX_IDENTITY", marker)
    monkeypatch.setattr(orc.sys, "platform", "linux")
    command = ["backend", flag, "option", flag, "prompt"]

    result = builder(command)  # type: ignore[operator]

    assert result.count(flag) == 1
    assert result[-1] == "prompt"


@pytest.mark.parametrize(
    ("backend", "mode", "expected"),
    [
        ("codex", "codex-missing-resume", "resume --help missing"),
        ("claude", "claude-missing-help", "--help missing"),
    ],
)
def test_begin_rejects_incompatible_backend_before_state_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    backend: str,
    mode: str,
    expected: str,
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    executable, _calls = fake_backend(tmp_path)
    monkeypatch.setenv("FAKE_MODE", mode)
    if backend == "codex":
        monkeypatch.setenv("CODEX_COMMAND", str(executable))
    else:
        monkeypatch.setenv("ORC_CLAUDE_COMMAND", str(executable))
    state_file = tmp_path / "state.json"
    args = orc.parse_args(
        [
            "--state-file",
            str(state_file),
            "begin",
            str(target),
            "TASK-014",
            "request",
            f"--{backend}",
        ]
    )
    monkeypatch.setattr(orc, "run_app", lambda *_: None)

    with pytest.raises(SystemExit, match=expected):
        orc.begin(args)
    assert not state_file.exists()


@pytest.mark.parametrize("backend", ["codex", "claude"])
def test_begin_compatible_backend_records_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, backend: str
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    executable, _calls = fake_backend(tmp_path)
    variable = "CODEX_COMMAND" if backend == "codex" else "ORC_CLAUDE_COMMAND"
    monkeypatch.setenv(variable, str(executable))
    state_file = tmp_path / "state.json"
    args = orc.parse_args(
        [
            "--state-file",
            str(state_file),
            "begin",
            str(target),
            "TASK-014",
            "request",
            f"--{backend}",
        ]
    )
    monkeypatch.setattr(orc, "run_app", lambda *_: None)

    orc.begin(args)

    record = orc.load_state(state_file)["TASK-014"]
    assert record["backend"] == backend
    assert record["backend_command"] == str(executable)
    assert record["backend_version"] == "fake-backend 1.2.3"


def test_preflight_output_and_version_bounds_are_deterministic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable, _calls = fake_backend(tmp_path)
    monkeypatch.setenv("FAKE_MODE", "long-version")
    with pytest.raises(SystemExit, match="backend version line exceeds 200 bytes"):
        orc.probe_codex([str(executable)])

    monkeypatch.setenv("FAKE_MODE", "help-overflow")
    with pytest.raises(
        SystemExit,
        match=(
            "backend codex executable.*failed help: "
            "preflight output exceeds 65536 bytes"
        ),
    ):
        orc.probe_codex([str(executable)])

    monkeypatch.setenv("FAKE_MODE", "invalid-version")
    assert orc.probe_codex([str(executable)]) == "v1.2.3�"

    monkeypatch.setenv("FAKE_MODE", "resume-overflow")
    with pytest.raises(
        SystemExit,
        match=(
            "backend codex executable.*failed resume help: "
            "preflight output exceeds 65536 bytes"
        ),
    ):
        orc.probe_codex([str(executable)])


@pytest.mark.parametrize(
    ("mode", "diagnostic"),
    [
        ("missing-version", "backend version is unknown"),
        ("nonzero", "failed version: exit status 7"),
    ],
)
def test_preflight_version_failures_are_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    diagnostic: str,
) -> None:
    executable, _calls = fake_backend(tmp_path)
    monkeypatch.setenv("FAKE_MODE", mode)
    with pytest.raises(SystemExit, match=diagnostic):
        orc.probe_codex([str(executable)])


def test_preflight_timeout_is_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable, _calls = fake_backend(tmp_path)
    monkeypatch.setenv("FAKE_MODE", "timeout")
    monkeypatch.setattr(orc, "SUBPROCESS_TIMEOUT_SECONDS", 0.05)
    with pytest.raises(
        SystemExit, match="failed version: timed out after 0.05 seconds"
    ):
        orc.probe_codex([str(executable)])


def test_preflight_rejects_invalid_backend_configuration() -> None:
    with pytest.raises(SystemExit, match="unsupported backend"):
        orc.preflight_backend("other", ["backend"])
    with pytest.raises(SystemExit, match="executable is missing"):
        orc.preflight_backend("codex", [])


def test_preflight_termination_escalates_when_needed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class StubbornProcess:
        pid = 123

        def terminate(self) -> None:
            self.terminated = True

        def kill(self) -> None:
            self.killed = True

        def wait(self, *, timeout: float) -> None:
            if not getattr(self, "killed", False):
                raise subprocess.TimeoutExpired("probe", timeout)

    process = StubbornProcess()
    monkeypatch.setattr(orc.os, "name", "nt")
    orc._terminate_preflight(process)  # type: ignore[arg-type]
    assert process.terminated is True
    assert process.killed is True


@pytest.mark.parametrize("backend", ["codex", "claude"])
def test_cli_resume_preflights_before_mutating_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, backend: str
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    executable, _calls = fake_backend(tmp_path)
    state_file = tmp_path / "state.json"
    orc.save_state(state_file, {"TASK-014": strict_record(target, backend, executable)})
    before = state_file.read_bytes()
    args = orc.parse_args(
        ["--state-file", str(state_file), "resume", "TASK-014", "continue"]
    )
    monkeypatch.setattr(orc, "run_app", lambda *_: None)

    orc.resume(args)
    assert state_file.read_bytes() != before
    assert orc.load_state(state_file)["TASK-014"]["backend"] == backend


@pytest.mark.parametrize(
    ("backend", "mode"),
    [("codex", "codex-missing-resume"), ("claude", "claude-missing-help")],
)
def test_cli_resume_failure_preserves_state_and_children(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    backend: str,
    mode: str,
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    executable, _calls = fake_backend(tmp_path)
    monkeypatch.setenv("FAKE_MODE", mode)
    state_file = tmp_path / "state.json"
    orc.save_state(state_file, {"TASK-014": strict_record(target, backend, executable)})
    before = state_file.read_bytes()
    args = orc.parse_args(
        ["--state-file", str(state_file), "resume", "TASK-014", "continue"]
    )
    monkeypatch.setattr(orc, "run_app", lambda *_: pytest.fail("must not launch"))

    with pytest.raises(SystemExit):
        orc.resume(args)
    assert state_file.read_bytes() == before


@pytest.mark.parametrize("backend", ["codex", "claude"])
def test_cli_resume_oserror_preserves_state_and_children(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, backend: str
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    missing = tmp_path / "missing backend"
    state_file = tmp_path / "state.json"
    orc.save_state(state_file, {"TASK-014": strict_record(target, backend, missing)})
    before = state_file.read_bytes()
    args = orc.parse_args(
        ["--state-file", str(state_file), "resume", "TASK-014", "continue"]
    )
    monkeypatch.setattr(orc, "run_app", lambda *_: pytest.fail("must not launch"))

    with pytest.raises(SystemExit, match=f"backend {backend} executable"):
        orc.resume(args)
    assert state_file.read_bytes() == before


@pytest.mark.parametrize("backend", ["codex", "claude"])
def test_in_place_resume_preflights_before_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, backend: str
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    executable, _calls = fake_backend(tmp_path)
    state_file = tmp_path / "state.json"
    orc.save_state(state_file, {"TASK-014": strict_record(target, backend, executable)})
    before = orc.load_state(state_file)["TASK-014"]
    app = orc.OrcApp.__new__(orc.OrcApp)
    app.args = argparse.Namespace(state_file=state_file)
    app.task_id = "TASK-014"
    app.sessions = {}
    app.resume_prompt_active = True
    app.update_status = lambda _status: None
    app.close_resume_prompt = lambda: None
    launched: list[str] = []
    app.launch_role = launched.append

    assert app.submit_resume_request("continue")
    assert launched == ["implementer"]
    saved = orc.load_state(state_file)["TASK-014"]
    assert saved["backend"] == before["backend"] == backend
    assert saved["backend_version"] == before["backend_version"]


@pytest.mark.parametrize(
    ("backend", "mode"),
    [("codex", "codex-missing-resume"), ("claude", "claude-missing-help")],
)
def test_in_place_resume_failure_preserves_state_and_children(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    backend: str,
    mode: str,
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    executable, _calls = fake_backend(tmp_path)
    monkeypatch.setenv("FAKE_MODE", mode)
    state_file = tmp_path / "state.json"
    orc.save_state(state_file, {"TASK-014": strict_record(target, backend, executable)})
    before = state_file.read_bytes()
    app = orc.OrcApp.__new__(orc.OrcApp)
    app.args = argparse.Namespace(state_file=state_file)
    app.task_id = "TASK-014"
    app.sessions = {}
    app.resume_prompt_active = True
    app.update_status = lambda _status: None
    app.close_resume_prompt = lambda: None
    launched: list[str] = []
    app.launch_role = launched.append

    assert not app.submit_resume_request("continue")
    assert launched == []
    assert app.sessions == {}
    assert state_file.read_bytes() == before


@pytest.mark.parametrize("backend", ["codex", "claude"])
def test_in_place_resume_oserror_preserves_state_and_children(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, backend: str
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    missing = tmp_path / "missing backend"
    state_file = tmp_path / "state.json"
    orc.save_state(state_file, {"TASK-014": strict_record(target, backend, missing)})
    before = state_file.read_bytes()
    app = orc.OrcApp.__new__(orc.OrcApp)
    app.args = argparse.Namespace(state_file=state_file)
    app.task_id = "TASK-014"
    app.sessions = {}
    app.resume_prompt_active = True
    statuses: list[str] = []
    app.update_status = statuses.append
    app.close_resume_prompt = lambda: None
    launched: list[str] = []
    app.launch_role = launched.append

    assert not app.submit_resume_request("continue")
    assert launched == []
    assert app.sessions == {}
    assert state_file.read_bytes() == before
    assert statuses and f"backend {backend} executable" in statuses[-1]


def test_in_place_resume_preflights_before_mutating_or_launching(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    executable, _calls = fake_backend(tmp_path)
    state_file = tmp_path / "state.json"
    orc.save_state(
        state_file, {"TASK-014": strict_record(target, "claude", executable)}
    )
    before = state_file.read_bytes()
    monkeypatch.setenv("FAKE_MODE", "claude-missing-help")
    app = orc.OrcApp.__new__(orc.OrcApp)
    app.args = argparse.Namespace(state_file=state_file)
    app.task_id = "TASK-014"
    app.sessions = {}
    app.resume_prompt_active = True
    statuses: list[str] = []
    launched: list[str] = []
    app.update_status = statuses.append
    app.close_resume_prompt = lambda: None
    app.launch_role = launched.append

    assert not app.submit_resume_request("continue")
    assert launched == []
    assert state_file.read_bytes() == before
    assert statuses and "backend claude executable" in statuses[-1]
