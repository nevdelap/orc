from __future__ import annotations

import argparse
import importlib.util
import os
import signal
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

ORC_SOURCE = Path(__file__).parents[1] / "orc"
spec = importlib.util.spec_from_loader(
    "orc_task015", SourceFileLoader("orc_task015", str(ORC_SOURCE))
)
assert spec is not None and spec.loader is not None
orc = importlib.util.module_from_spec(spec)
sys.modules["orc_task015"] = orc
spec.loader.exec_module(orc)


def strict_record(target: Path) -> dict[str, object]:
    return {
        "schema_version": orc.STATE_SCHEMA_VERSION,
        "revision": 1,
        "task_id": "TASK-015",
        "status": "active",
        "phase": "implementer",
        "round": 1,
        "target_directory": str(target),
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
    }


def child_command(*, ignore_term: bool = True) -> list[str]:
    code = "import time; time.sleep(30)"
    if ignore_term:
        code = (
            "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
            "time.sleep(30)"
        )
    return [sys.executable, "-c", code]


def app_with_child(
    tmp_path: Path, *, ignore_term: bool = True
) -> tuple[object, Path, int, object]:
    target = tmp_path / "target"
    target.mkdir()
    state_file = tmp_path / "state.json"
    orc.save_state(state_file, {"TASK-015": strict_record(target)})
    app = orc.OrcApp.__new__(orc.OrcApp)
    app.args = argparse.Namespace(state_file=state_file)
    app.task_id = "TASK-015"
    app.sessions = {}
    app.retired_sessions = []
    app.event_loop = None
    app._cleanup_request = None
    app._terminal_fd = None
    app._terminal_attributes = None
    app._previous_signal_handlers = {}
    app._cleanup_started = False
    pid, master_fd = app.fork_codex(
        child_command(ignore_term=ignore_term), os.environ.copy(), target
    )
    session = orc.ChildSession("implementer", pid, master_fd, object())
    app.sessions["implementer"] = session
    return app, state_file, pid, session


@pytest.mark.integration
def test_ctrl_q_cleanup_stops_group_and_persists_resumeable_record(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    state_file = tmp_path / "state.json"
    record = strict_record(target)
    orc.save_state(state_file, {"TASK-015": record})

    app = orc.OrcApp.__new__(orc.OrcApp)
    app.args = argparse.Namespace(state_file=state_file)
    app.task_id = "TASK-015"
    app.sessions = {}
    app.retired_sessions = []
    app.event_loop = None
    app._cleanup_request = ("manual_pause", "operator quit", "operator quit")
    app._terminal_fd = None
    app._terminal_attributes = None
    app._previous_signal_handlers = {}
    app._cleanup_started = False
    pid, master_fd = app.fork_codex(child_command(), os.environ.copy(), target)
    session = orc.ChildSession("implementer", pid, master_fd, object())
    app.sessions["implementer"] = session
    record["role_launches"] = {
        "implementer": {
            "role": "implementer",
            "phase": "implementer",
            "generation": 1,
            "launch_token": "token",
            "can_report": True,
            "live_child": True,
            "pid": pid,
        }
    }
    record["role_generations"] = {"implementer": 1, "reviewer": 0}
    orc.save_state(state_file, {"TASK-015": record})

    app.cleanup("operator quit", stop_reason="manual_pause")
    app.cleanup("second cleanup", stop_reason="orchestrator_exit")

    saved = orc.load_state(state_file)["TASK-015"]
    assert saved["status"] == "stopped"
    assert saved["phase"] == "stopped"
    assert saved["stop_reason"] == "manual_pause"
    assert saved["stop_diagnostic"] == "operator quit"
    assert saved["role_states"] == {"implementer": "inactive", "reviewer": "inactive"}
    assert saved["role_launches"]["implementer"]["can_report"] is False
    assert session.master_fd == -1
    assert session.exited is True
    with pytest.raises(ChildProcessError):
        os.waitpid(pid, os.WNOHANG)

    resumed = dict(saved)
    orc.resume_task_record(resumed, "continue")
    assert resumed["status"] == "active"
    assert "stop_diagnostic" not in resumed


@pytest.mark.integration
def test_pty_read_error_uses_orchestrator_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, state_file, pid, session = app_with_child(tmp_path)
    monkeypatch.setattr(
        orc.os,
        "read",
        lambda *_args: (_ for _ in ()).throw(OSError(orc.errno.EIO, "pty lost")),
    )

    app.read_session(session)

    saved = orc.load_state(state_file)["TASK-015"]
    assert saved["status"] == "stopped"
    assert saved["phase"] == "stopped"
    assert saved["stop_reason"] == "orchestrator_exit"
    assert "PTY read error" in saved["stop_diagnostic"]
    assert saved["role_states"] == {"implementer": "inactive", "reviewer": "inactive"}
    assert session.master_fd == -1
    assert session.exited is True
    with pytest.raises(ChildProcessError):
        os.waitpid(pid, os.WNOHANG)


@pytest.mark.integration
def test_retired_pty_error_does_not_stop_replacement_workflow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, state_file, pid, session = app_with_child(tmp_path)
    state = orc.load_state(state_file)
    record = state["TASK-015"]
    record["phase"] = "reviewer"
    record["role_states"] = {"implementer": "waiting", "reviewer": "active"}
    orc.save_state(state_file, state)
    session.retired = True
    app.sessions = {}
    app.retired_sessions = [session]
    app.cleanup = lambda *_args, **_kwargs: pytest.fail(
        "retired PTY error must not stop the active workflow"
    )
    monkeypatch.setattr(
        orc.os,
        "read",
        lambda *_args: (_ for _ in ()).throw(OSError(orc.errno.EIO, "late pty error")),
    )

    try:
        app.read_session(session)
        saved = orc.load_state(state_file)["TASK-015"]
        assert saved["status"] == "active"
        assert saved["phase"] == "reviewer"
        assert session.master_fd == -1
    finally:
        try:
            os.killpg(pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            pass
        try:
            os.waitpid(pid, 0)
        except ChildProcessError:
            pass


@pytest.mark.integration
@pytest.mark.parametrize("signum", [signal.SIGINT, signal.SIGHUP, signal.SIGTERM])
def test_real_signal_uses_orchestrator_cleanup(tmp_path: Path, signum: int) -> None:
    app, state_file, pid, session = app_with_child(tmp_path, ignore_term=False)
    app.exit = lambda: None
    app._install_signal_handlers()

    os.kill(os.getpid(), signum)

    saved = orc.load_state(state_file)["TASK-015"]
    assert saved["status"] == "stopped"
    assert saved["stop_reason"] == "orchestrator_exit"
    assert signal.Signals(signum).name in saved["stop_diagnostic"]
    assert session.master_fd == -1
    assert session.exited is True
    with pytest.raises(ChildProcessError):
        os.waitpid(pid, os.WNOHANG)


def test_signal_cleanup_is_idempotent_and_restores_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    state_file = tmp_path / "state.json"
    orc.save_state(state_file, {"TASK-015": strict_record(target)})
    app = orc.OrcApp.__new__(orc.OrcApp)
    app.args = argparse.Namespace(state_file=state_file)
    app.task_id = "TASK-015"
    app.sessions = {}
    app.retired_sessions = []
    app.event_loop = None
    app._cleanup_started = False
    app._cleanup_request = None
    app._terminal_fd = 9
    app._terminal_attributes = [1, 2, 3]
    app._previous_signal_handlers = {}
    restored: list[tuple[int, int, list[int]]] = []
    monkeypatch.setattr(
        orc.termios,
        "tcsetattr",
        lambda fd, action, attrs: restored.append((fd, action, attrs)),
    )
    exited: list[bool] = []
    monkeypatch.setattr(app, "exit", lambda: exited.append(True))

    app._handle_signal(signal.SIGTERM, None)
    app._handle_signal(signal.SIGTERM, None)

    saved = orc.load_state(state_file)["TASK-015"]
    assert saved["status"] == "stopped"
    assert saved["stop_reason"] == "orchestrator_exit"
    assert saved["stop_diagnostic"] == "received SIGTERM"
    assert restored == [(9, orc.termios.TCSADRAIN, [1, 2, 3])]
    assert exited == [True]


def test_cleanup_persistence_failure_still_closes_pty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    state_file = tmp_path / "state.json"
    target = tmp_path / "target"
    target.mkdir()
    orc.save_state(state_file, {"TASK-015": strict_record(target)})
    app = orc.OrcApp.__new__(orc.OrcApp)
    app.args = argparse.Namespace(state_file=state_file)
    app.task_id = "TASK-015"
    app.sessions = {}
    app.retired_sessions = []
    app.event_loop = None
    app._cleanup_started = False
    app._cleanup_request = None
    app._terminal_fd = None
    app._terminal_attributes = None
    app._previous_signal_handlers = {}
    closed: list[int] = []
    session = argparse.Namespace(pid=123, master_fd=8, exited=True)
    app.sessions["implementer"] = session
    monkeypatch.setattr(
        orc,
        "mutate_task_state",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            SystemExit("state lock failed")
        ),
    )
    monkeypatch.setattr(orc.os, "close", closed.append)

    app.cleanup("uncaught exception", diagnostic="uncaught RuntimeError: boom")

    assert closed == [8]
    assert session.master_fd == -1
    assert "could not persist cleanup state" in capsys.readouterr().err


def test_cleanup_helpers_handle_terminal_records_and_signal_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    state_file = tmp_path / "state.json"
    record = strict_record(target)
    record["status"] = "completed"
    record["phase"] = "complete"
    record["stop_reason"] = "completion"
    record["role_states"] = {"implementer": "inactive", "reviewer": "inactive"}
    orc.save_state(state_file, {"TASK-015": record})
    app = orc.OrcApp.__new__(orc.OrcApp)
    app.args = argparse.Namespace(state_file=state_file)
    app.task_id = "TASK-015"
    app.sessions = {}
    app.retired_sessions = []
    app.event_loop = None
    app._cleanup_started = False
    app._cleanup_request = None
    app._terminal_fd = None
    app._terminal_attributes = None
    app._previous_signal_handlers = {}
    app.cleanup("late signal")
    assert orc.load_state(state_file)["TASK-015"] == record

    calls: list[tuple[int, int]] = []
    monkeypatch.setattr(
        orc.os,
        "killpg",
        lambda *_args: (_ for _ in ()).throw(OSError("no process group")),
    )
    monkeypatch.setattr(orc.os, "kill", lambda pid, signum: calls.append((pid, signum)))
    orc.OrcApp._signal_child_group(argparse.Namespace(pid=33), orc.signal.SIGTERM)
    orc.OrcApp._signal_child_group(argparse.Namespace(pid=0), orc.signal.SIGTERM)
    assert calls == [(33, orc.signal.SIGTERM)]
    monkeypatch.setattr(
        orc.os,
        "kill",
        lambda *_args: (_ for _ in ()).throw(OSError("already gone")),
    )
    orc.OrcApp._signal_child_group(argparse.Namespace(pid=34), orc.signal.SIGTERM)


def test_run_app_exception_uses_cleanup_before_reraising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instances: list[object] = []

    class FailingApp:
        def __init__(self, _args: object, _task: str) -> None:
            self._cleanup_started = False
            self.calls: list[str] = []
            instances.append(self)

        def run(self) -> None:
            raise RuntimeError("boom")

        def cleanup(self, trigger: str, **_kwargs: object) -> None:
            self.calls.append(trigger)
            self._cleanup_started = True

    monkeypatch.setattr(orc, "OrcApp", FailingApp)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    with pytest.raises(RuntimeError, match="boom"):
        orc.run_app(argparse.Namespace(), "TASK-015")
    # The exception handler, rather than the finally fallback, must own the
    # cleanup for an injected failure.
    assert instances[0].calls == ["uncaught RuntimeError"]  # type: ignore[attr-defined]


@pytest.mark.integration
@pytest.mark.parametrize(
    "failure",
    [RuntimeError("boom"), EOFError("terminal disconnected")],
    ids=["uncaught-exception", "terminal-disconnect"],
)
def test_real_run_app_failure_cleans_up_child_and_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: BaseException,
) -> None:
    app, state_file, pid, session = app_with_child(tmp_path, ignore_term=False)

    def fail() -> None:
        raise failure

    app.run = fail
    monkeypatch.setattr(orc, "OrcApp", lambda *_args: app)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    with pytest.raises(type(failure), match=str(failure)):
        orc.run_app(argparse.Namespace(), "TASK-015")

    saved = orc.load_state(state_file)["TASK-015"]
    assert saved["status"] == "stopped"
    assert saved["stop_reason"] == "orchestrator_exit"
    assert type(failure).__name__ in saved["stop_diagnostic"]
    assert session.master_fd == -1
    assert session.exited is True
    with pytest.raises(ChildProcessError):
        os.waitpid(pid, os.WNOHANG)


def test_terminal_capture_and_signal_handlers_are_restored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = orc.OrcApp.__new__(orc.OrcApp)
    app._previous_signal_handlers = {}
    app._terminal_fd = None
    app._terminal_attributes = None
    monkeypatch.setattr(sys.stdin, "fileno", lambda: 7)
    monkeypatch.setattr(orc.os, "isatty", lambda _fd: True)
    monkeypatch.setattr(orc.termios, "tcgetattr", lambda _fd: [4, 5])
    app._capture_terminal_state()
    assert app._terminal_fd == 7
    assert app._terminal_attributes == [4, 5]

    handlers: dict[int, object] = {}
    monkeypatch.setattr(orc.signal, "getsignal", lambda signum: signum)
    monkeypatch.setattr(
        orc.signal,
        "signal",
        lambda signum, handler: handlers.__setitem__(signum, handler),
    )
    app._install_signal_handlers()
    assert set(handlers) == {orc.signal.SIGINT, orc.signal.SIGHUP, orc.signal.SIGTERM}
    app._restore_signal_handlers()
    assert app._previous_signal_handlers == {}


def test_cleanup_tolerates_reader_and_terminal_restore_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = orc.OrcApp.__new__(orc.OrcApp)
    app.args = argparse.Namespace(state_file=tmp_path / "missing.json")
    app.task_id = "TASK-015"
    app.sessions = {}
    app.retired_sessions = []
    app.event_loop = None
    app._cleanup_started = False
    app._cleanup_request = None
    app._terminal_fd = 9
    app._terminal_attributes = [1]
    app._previous_signal_handlers = {}
    app.close_master_reader = lambda _session: (_ for _ in ()).throw(RuntimeError())
    monkeypatch.setattr(
        orc.termios,
        "tcsetattr",
        lambda *_args: (_ for _ in ()).throw(OSError("terminal gone")),
    )
    app.sessions["implementer"] = argparse.Namespace(pid=1, master_fd=-1, exited=True)
    app.cleanup("terminal disconnect")
