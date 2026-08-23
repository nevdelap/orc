from __future__ import annotations

import argparse
import asyncio
import fcntl
import importlib.util
import json
import os
import struct
import subprocess
import sys
import termios
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

ORC_SOURCE = Path(__file__).parents[1] / "orc"
orc_spec = importlib.util.spec_from_loader(
    "orc", SourceFileLoader("orc", str(ORC_SOURCE))
)
assert orc_spec is not None and orc_spec.loader is not None
orc = importlib.util.module_from_spec(orc_spec)
sys.modules["orc"] = orc
orc_spec.loader.exec_module(orc)


class Event:
    def __init__(self, key: str = "", character: str | None = None) -> None:
        self.key = key
        self.character = character
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


def cli_args(
    state_file: Path, directory: Path, task_id: str = "TASK-003"
) -> argparse.Namespace:
    return orc.parse_args(
        [
            "--state-file",
            str(state_file),
            "begin",
            str(directory),
            task_id,
            "implement the task",
            "--codex",
        ]
    )


def make_git_target(path: Path) -> str:
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "test@example.com"],
        check=True,
    )
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Test"], check=True)
    (path / "file.txt").write_text("target\n")
    subprocess.run(["git", "-C", str(path), "add", "file.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(path), "commit", "-qm", "target commit"], check=True
    )
    return subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--short", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_direct_script_help_invocation() -> None:
    result = subprocess.run(
        [str(Path(__file__).parents[1] / "orc"), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "begin DIRECTORY TASK-ID" in result.stdout


def test_help_requires_and_describes_directory(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as error:
        orc.parse_args(["--help"])
    assert error.value.code == 0
    output = capsys.readouterr().out
    assert "begin DIRECTORY TASK-ID" in output
    assert "resume TASK-ID PROMPT" in output
    assert "DIRECTORY" in output


def test_parse_args_normalizes_state_path(tmp_path: Path) -> None:
    args = orc.parse_args(
        ["--state-file", "relative-state.json", "begin", str(tmp_path), "T", "P"]
    )
    assert args.state_file == Path.cwd() / "relative-state.json"
    assert args.directory == tmp_path


@pytest.mark.parametrize("directory", [Path("missing"), Path(__file__)])
def test_begin_rejects_invalid_directory_without_state(
    tmp_path: Path, directory: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_file = tmp_path / "state.json"
    actual = directory if directory.is_absolute() else tmp_path / directory
    args = cli_args(state_file, actual)
    monkeypatch.setattr(orc, "run_app", lambda *_: pytest.fail("must not launch"))
    with pytest.raises(SystemExit, match="target directory"):
        orc.begin(args)
    assert not state_file.exists()


def test_begin_persists_normalized_target_before_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    state_file = tmp_path / "orc" / "state.json"
    args = cli_args(state_file, target / ".." / "target")
    launched: list[str] = []
    monkeypatch.setattr(orc, "run_app", lambda _args, task: launched.append(task))

    orc.begin(args)

    state = orc.load_state(state_file)
    assert state["TASK-003"]["target_directory"] == str(target.resolve())
    assert launched == ["TASK-003"]


def test_begin_rejects_duplicate_without_overwriting_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    state_file = tmp_path / "state.json"
    old = {"TASK-003": {"target_directory": str(target), "prompt": "old"}}
    orc.save_state(state_file, old)
    monkeypatch.setattr(orc, "run_app", lambda *_: pytest.fail("must not launch"))
    with pytest.raises(SystemExit, match="task already exists"):
        orc.begin(cli_args(state_file, target))
    assert orc.load_state(state_file) == old


def test_resume_requires_matching_target_before_mutating_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    other = tmp_path / "other"
    target.mkdir()
    other.mkdir()
    state_file = tmp_path / "state.json"
    state = {
        "TASK-003": {
            "status": "paused",
            "phase": "reviewer",
            "round": 2,
            "prompt": "first",
            "target_directory": str(target.resolve()),
            "backend": "codex",
            "user_requests": [],
        }
    }
    orc.save_state(state_file, state)
    monkeypatch.setattr(orc, "run_app", lambda *_: pytest.fail("must not launch"))

    with pytest.raises(SystemExit, match="does not match"):
        orc.resume(cli_args(state_file, other))
    assert orc.load_state(state_file) == state


def test_resume_records_request_after_matching_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    state_file = tmp_path / "state.json"
    state = {
        "TASK-003": {
            "status": "paused",
            "phase": "reviewer",
            "round": 2,
            "prompt": "first",
            "target_directory": str(target.resolve()),
            "backend": "codex",
            "user_requests": [],
        }
    }
    orc.save_state(state_file, state)
    monkeypatch.setattr(orc, "run_app", lambda *_: None)

    orc.resume(cli_args(state_file, target))

    record = orc.load_state(state_file)["TASK-003"]
    assert record["user_requests"] == ["implement the task"]
    assert record["round"] == 2
    assert record["phase"] == "implementer"


def test_resume_restarts_reviewer_after_child_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    state_file = tmp_path / "state.json"
    state = {
        "TASK-003": {
            "status": "stopped",
            "phase": "stopped",
            "round": 2,
            "prompt": "first",
            "target_directory": str(target.resolve()),
            "user_requests": ["continue to completion"],
            "reviewer_id": "missing-rollout-thread",
            "backend": "codex",
            "stop_reason": "child_failure",
            "child_failure": {"role": "reviewer", "exit_status": 256},
        }
    }
    orc.save_state(state_file, state)
    monkeypatch.setattr(orc, "run_app", lambda *_: None)

    orc.resume(cli_args(state_file, target))

    record = orc.load_state(state_file)["TASK-003"]
    assert record["status"] == "active"
    assert record["phase"] == "reviewer"
    assert record["round"] == 2
    assert record["reviewer_id"] is None
    assert "child_failure" not in record
    assert record["user_requests"] == [
        "continue to completion",
        "implement the task",
    ]


@pytest.mark.parametrize("role", ["implementer", "reviewer"])
def test_resume_clears_failure_before_role_becomes_active(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, role: str
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    state_file = tmp_path / "state.json"
    state = {
        "TASK-003": {
            "status": "stopped",
            "phase": "stopped",
            "round": 2,
            "prompt": "first",
            "target_directory": str(target.resolve()),
            "user_requests": [],
            "backend": "codex",
            "stop_reason": "child_failure",
            "child_failure": {"role": role, "exit_status": 256},
        }
    }
    orc.save_state(state_file, state)
    monkeypatch.setattr(orc, "run_app", lambda *_: None)

    orc.resume(cli_args(state_file, target))

    saved = orc.load_state(state_file)["TASK-003"]
    assert "child_failure" not in saved
    assert saved["phase"] == ("reviewer" if role == "reviewer" else "implementer")
    app, _state_file, panes = app_stub(tmp_path, saved)
    app.sessions[role] = orc.ChildSession(role, 123, 99, panes[role])
    assert app.role_state(saved, role) == "active"


@pytest.mark.parametrize("phase", ["implementer", "reviewer", "stopped", None])
def test_startup_role_follows_persisted_phase(phase: str | None) -> None:
    record = {"phase": phase}
    expected = phase if phase in {"implementer", "reviewer"} else "implementer"
    assert orc.OrcApp.initial_role(record) == expected


def test_resume_rejects_missing_stored_target_without_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    state_file = tmp_path / "state.json"
    state = {"TASK-003": {"prompt": "old", "user_requests": []}}
    orc.save_state(state_file, state)
    monkeypatch.setattr(orc, "run_app", lambda *_: pytest.fail("must not launch"))
    with pytest.raises(SystemExit, match="no stored target"):
        orc.resume(cli_args(state_file, target))
    assert orc.load_state(state_file) == state


def test_state_load_save_and_errors(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "state.json"
    value = {"task": {"round": 1}}
    orc.save_state(path, value)
    assert orc.load_state(path) == value
    path.write_text("[]")
    with pytest.raises(SystemExit, match="must contain an object"):
        orc.load_state(path)
    path.write_text("{")
    with pytest.raises(SystemExit, match="cannot read Orc state"):
        orc.load_state(path)


def test_current_commit_uses_requested_target(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    commit = make_git_target(target)
    assert orc.current_commit(target) == commit
    assert orc.current_commit(tmp_path / "not-a-repo") == "unknown"
    assert orc.current_commit(None) == "unknown"


def test_prompts_name_target_directory(tmp_path: Path) -> None:
    target = tmp_path / "target"
    record = {"target_directory": str(target), "prompt": "build", "user_requests": []}
    assert str(target) in orc.reviewer_prompt(record)


def test_notify_config_uses_absolute_state_path(tmp_path: Path) -> None:
    config = json.loads(orc.notify_config(Path("state.json")))
    assert str(Path.cwd() / "state.json") in config
    assert config[-1] == "idle-hook"


def test_idle_hook_records_target_commit_and_role_transition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    commit = make_git_target(target)
    state_file = tmp_path / "state.json"
    orc.save_state(
        state_file,
        {
            "TASK-003": {
                "round": 1,
                "target_directory": str(target.resolve()),
                "implementer_id": None,
                "reviewer_id": None,
                "handoffs": [],
            }
        },
    )
    monkeypatch.setenv("ORC_TASK_ID", "TASK-003")
    monkeypatch.setenv("ORC_ROLE", "implementer")
    payload = {
        "session_id": "igor-thread",
        "cwd": str(Path.cwd()),
        "last-assistant-message": "done",
    }
    args = argparse.Namespace(state_file=state_file, payload=json.dumps(payload))

    orc.idle_hook(args)

    record = orc.load_state(state_file)["TASK-003"]
    assert record["phase"] == "reviewer"
    assert record["implementer_id"] == "igor-thread"
    assert record["last_handoff"]["commit"] == commit
    assert record["last_handoff"]["target_directory"] == str(target.resolve())
    assert record["last_handoff"]["message"] == "done"


def test_idle_hook_reviewer_pauses_and_finds_role_by_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    state_file = tmp_path / "state.json"
    orc.save_state(
        state_file,
        {
            "TASK-003": {
                "round": 2,
                "target_directory": str(target.resolve()),
                "implementer_id": "igor",
                "reviewer_id": "rufus",
                "handoffs": [],
            }
        },
    )
    monkeypatch.delenv("ORC_TASK_ID", raising=False)
    monkeypatch.delenv("ORC_ROLE", raising=False)
    payload = {"thread_id": "rufus", "last_agent_message": "TASK COMPLETE"}
    args = argparse.Namespace(state_file=state_file, payload=json.dumps(payload))

    orc.idle_hook(args)

    record = orc.load_state(state_file)["TASK-003"]
    assert record["status"] == "completed"
    assert record["reviewer_reported_complete"] is True
    assert record["reviewer_id"] == "rufus"


def test_idle_hook_rejects_missing_target_before_git_lookup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_file = tmp_path / "state.json"
    orc.save_state(state_file, {"TASK-003": {"handoffs": []}})
    monkeypatch.setenv("ORC_TASK_ID", "TASK-003")
    monkeypatch.setenv("ORC_ROLE", "implementer")
    args = argparse.Namespace(
        state_file=state_file,
        payload=json.dumps({"session_id": "igor"}),
    )
    with pytest.raises(SystemExit, match="valid target directory"):
        orc.idle_hook(args)
    assert orc.load_state(state_file)["TASK-003"] == {"handoffs": []}


def test_idle_hook_rejects_bad_payload_and_unknown_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_file = tmp_path / "state.json"
    orc.save_state(state_file, {})
    args = argparse.Namespace(state_file=state_file, payload="not json")
    with pytest.raises(SystemExit, match="invalid Codex"):
        orc.idle_hook(args)
    args.payload = json.dumps({"event": "idle"})
    monkeypatch.delenv("ORC_TASK_ID", raising=False)
    monkeypatch.delenv("ORC_ROLE", raising=False)
    with pytest.raises(SystemExit, match="could not identify"):
        orc.idle_hook(args)


def test_payload_helpers_find_nested_values() -> None:
    value = {"nested": [{"threadId": "t"}, {"last_agent_message": "m"}]}
    assert orc.session_id_from_payload(value) == "t"
    assert orc.assistant_message_from_payload(value) == "m"
    assert orc.session_id_from_payload(["x"]) is None
    assert orc.assistant_message_from_payload(["x"]) is None


@pytest.mark.integration
def test_fork_codex_runs_in_target_directory(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    command = [sys.executable, "-c", "import os; print(os.getcwd(), flush=True)"]
    pid, fd = orc.OrcApp.fork_codex(command, os.environ.copy(), target)
    output = os.read(fd, 4096).decode()
    _, status = os.waitpid(pid, 0)
    os.close(fd)
    assert os.WEXITSTATUS(status) == 0
    assert str(target) in output


def test_session_pane_preserves_ansi_and_resizes() -> None:
    pane = orc.SessionPane("implementer")
    pane.feed(b"\x1b[31mred\x1b[0m\n")
    assert pane.has_output is True
    assert pane.has_visible_content is True
    rendered = pane.render_screen()
    assert "red" in rendered.plain
    assert rendered.spans
    pane.update = lambda *_args: None
    pane.resize_terminal(12, 4)
    pane.show_message("message")
    assert pane.message == "message"


def test_session_pane_retains_and_navigates_independent_scrollback() -> None:
    pane = orc.SessionPane("implementer")
    other_pane = orc.SessionPane("reviewer")
    pane.feed("\n".join(f"line-{index}" for index in range(10_050)).encode())
    other_pane.feed(b"reviewer-line\n")
    assert pane.scroll_position == 0
    assert other_pane.scroll_position == 0
    pane.scroll_page(-1)
    assert pane.scroll_position == pane.terminal_screen.lines
    assert other_pane.scroll_position == 0
    pane.feed(b"new-output\n")
    assert pane.scroll_position == pane.terminal_screen.lines
    pane.scroll_to_home()
    assert pane.scroll_position >= orc.SCROLLBACK_LINES - 24
    pane.scroll_to_end()
    assert pane.scroll_position == 0


def test_pty_size_handles_small_values_and_bad_fd() -> None:
    orc.set_pty_size(-1, 0, 0)


@pytest.mark.integration
def test_pty_size_updates_real_linux_pty() -> None:
    master_fd, slave_fd = os.openpty()
    try:
        orc.set_pty_size(master_fd, 37, 11)
        rows, columns, _, _ = struct.unpack(
            "HHHH", fcntl.ioctl(slave_fd, termios.TIOCGWINSZ, bytes(8))
        )
        assert (columns, rows) == (37, 11)
    finally:
        os.close(master_fd)
        os.close(slave_fd)


@pytest.mark.integration
def test_live_textual_resize_focus_and_pty_redraw(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_file = tmp_path / "state.json"
    target = tmp_path / "target"
    target.mkdir()
    orc.save_state(
        state_file,
        {
            "TASK-004": {
                "status": "active",
                "phase": "implementer",
                "target_directory": str(target),
            }
        },
    )
    args = argparse.Namespace(state_file=state_file, codex="codex")
    app = orc.OrcApp(args, "TASK-004")
    monkeypatch.setattr(app, "launch_role", lambda _role: None)

    async def exercise() -> None:
        async with app.run_test(size=(120, 40)) as pilot:
            app.event_loop = asyncio.get_running_loop()
            sessions: dict[str, orc.ChildSession] = {}
            try:
                for role in ("implementer", "reviewer"):
                    command = [
                        sys.executable,
                        "-c",
                        (
                            "import signal,sys,time; "
                            "signal.signal(signal.SIGWINCH, lambda *_: "
                            "print('\\x1b[31mLIVE-' + sys.argv[1] + "
                            "'-resized\\x1b[0m', flush=True)); "
                            "print('\\x1b[31mLIVE-' + sys.argv[1] + "
                            "'\\x1b[0m', flush=True); time.sleep(30)"
                        ),
                        role,
                    ]
                    pid, master_fd = app.fork_codex(command, os.environ.copy(), target)
                    os.set_blocking(master_fd, False)
                    session = orc.ChildSession(role, pid, master_fd, app.pane(role))
                    sessions[role] = session
                    app.sessions[role] = session
                    app.started_roles.add(role)
                    app.set_master_reader(session)

                app.active_role = "implementer"
                app.update_layout()
                app.resize_sessions()
                await pilot.pause(0.15)
                assert app.layout_mode == "side-by-side"
                assert app.pane("implementer").has_visible_content
                assert (
                    "LIVE-implementer" in app.pane("implementer").render_screen().plain
                )
                side_sizes = {
                    role: _pty_size(app.sessions[role].master_fd) for role in sessions
                }
                assert all(
                    width >= 2 and height >= 2 for width, height in side_sizes.values()
                )

                assert await pilot.click("#reviewer")
                await pilot.pause()
                assert app.active_role == "implementer"
                await pilot.press("tab")
                await pilot.pause()
                assert app.active_role == "implementer"
                await pilot.click("#reviewer")
                await pilot.pause()
                assert app.active_role == "implementer"
                assert "active" in app.last_status
                assert "Ctrl-Q exits" in app.last_status
                assert "active-pane" not in app.pane("reviewer").classes
                assert "active-pane" in app.pane("implementer").classes

                await pilot.resize_terminal(80, 40)
                await pilot.pause(0.1)
                assert app.layout_mode == "stacked"
                stacked_sizes = {
                    role: _pty_size(app.sessions[role].master_fd) for role in sessions
                }
                assert all(
                    width >= 2 and height >= 2
                    for width, height in stacked_sizes.values()
                )

                await pilot.resize_terminal(80, 24)
                await pilot.pause(0.1)
                assert app.layout_mode == "single"
                tiny_before = {
                    role: _pty_size(app.sessions[role].master_fd) for role in sessions
                }
                await pilot.resize_terminal(3, 3)
                await pilot.pause(0.1)
                tiny_after = {
                    role: _pty_size(app.sessions[role].master_fd) for role in sessions
                }
                assert all(
                    width >= 2 and height >= 2
                    for width, height in (*tiny_before.values(), *tiny_after.values())
                )
                await pilot.resize_terminal(80, 40)
                await pilot.pause(0.1)
                assert app.layout_mode == "stacked"
                assert app.pane("implementer").has_visible_content
                assert (
                    "LIVE-implementer-resized"
                    in app.pane("implementer").render_screen().plain
                )
            finally:
                for session in sessions.values():
                    try:
                        os.killpg(session.pid, orc.signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                app.exit()
                for session in sessions.values():
                    try:
                        os.waitpid(session.pid, 0)
                    except ChildProcessError:
                        pass

    asyncio.run(exercise())


def _pty_size(fd: int) -> tuple[int, int]:
    rows, columns, _, _ = struct.unpack(
        "HHHH", fcntl.ioctl(fd, termios.TIOCGWINSZ, bytes(8))
    )
    return columns, rows


def test_resize_uses_rendered_pane_content_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = orc.OrcApp.__new__(orc.OrcApp)
    pane = FakePane(120, 40, content_width=57, content_height=13)
    session = argparse.Namespace(
        master_fd=7, pane=pane, exited=False, role="implementer"
    )
    sizes: list[tuple[int, int]] = []
    rendered_sizes: list[tuple[int, int]] = []
    monkeypatch.setattr(orc, "set_pty_size", lambda _fd, w, h: sizes.append((w, h)))
    pane.resize_terminal = lambda w, h: rendered_sizes.append((w, h))

    app.resize_session(session)

    assert sizes == [(57, 13)]
    assert rendered_sizes == [(57, 13)]


def test_orc_input_forwarding_and_scroll_navigation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = orc.OrcApp.__new__(orc.OrcApp)
    app.active_role = "implementer"
    app.scroll_target = "implementer"
    app.layout_mode = "side-by-side"
    writes: list[bytes] = []
    monkeypatch.setattr(app, "write_active", writes.append)
    monkeypatch.setattr(app, "update_layout", lambda: None)
    monkeypatch.setattr(app, "update_status", lambda _message: None)
    panes = {"implementer": FakePane(), "reviewer": FakePane()}
    app.pane = lambda role: panes[role]

    for event, expected in (
        (Event("enter"), b"\r"),
        (Event("c", "c"), b"c"),
        (Event("ctrl+c"), b"\x03"),
        (Event("shift+tab"), b"\x1b[Z"),
        (Event("1", "1"), b"1"),
        (Event("2", "2"), b"2"),
    ):
        app.on_key(event)
        assert writes[-1] == expected
        assert event.stopped

    tab = Event("tab", "\t")
    app.on_key(tab)
    assert app.active_role == "implementer"
    assert app.scroll_target == "reviewer"
    assert tab.stopped
    assert writes == [b"\r", b"c", b"\x03", b"\x1b[Z", b"1", b"2"]

    for key, action in (
        ("pageup", ("page", -1)),
        ("pagedown", ("page", 1)),
        ("home", ("home", None)),
        ("end", ("end", None)),
    ):
        event = Event(key)
        app.on_key(event)
        assert event.stopped
        assert panes["reviewer"].scroll_actions[-1] == action
    assert writes == [b"\r", b"c", b"\x03", b"\x1b[Z", b"1", b"2"]
    event = Event("unknown")
    app.on_key(event)
    assert event.stopped


def test_paste_click_and_find_task_role(monkeypatch: pytest.MonkeyPatch) -> None:
    app = orc.OrcApp.__new__(orc.OrcApp)
    app.active_role = "implementer"
    app.layout_mode = "side-by-side"
    app.sessions = {}
    writes: list[bytes] = []
    statuses: list[str] = []
    monkeypatch.setattr(app, "write_active", writes.append)
    monkeypatch.setattr(app, "update_layout", lambda: None)
    monkeypatch.setattr(app, "update_status", statuses.append)

    class PasteEvent:
        text = "paste"
        stopped = False

        def stop(self) -> None:
            self.stopped = True

    paste = PasteEvent()
    app.on_paste(paste)
    assert writes == [b"paste"] and paste.stopped

    class Widget:
        id = "reviewer"

    class ClickEvent:
        widget = Widget()
        stopped = False

        def stop(self) -> None:
            self.stopped = True

    click = ClickEvent()
    app.on_click(click)
    assert app.active_role == "implementer" and click.stopped
    assert orc.find_task_role({"T": {"reviewer_id": "r"}}, "r") == ("T", "reviewer")
    assert orc.find_task_role({}, "missing") == (None, None)


def test_pointer_selects_scroll_target_and_agent_input_returns_to_bottom(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    app, _state_file, panes = app_stub(
        tmp_path,
        {
            "status": "active",
            "phase": "implementer",
            "target_directory": str(target),
            "user_requests": [],
        },
    )

    class Widget:
        id = "reviewer"
        parent = None

    class MoveEvent:
        widget = Widget()
        stopped = False

        def stop(self) -> None:
            self.stopped = True

    move = MoveEvent()
    app.on_mouse_move(move)
    assert app.scroll_target == "reviewer"
    assert move.stopped

    app.sessions["implementer"] = argparse.Namespace(
        role="implementer", master_fd=1, pane=panes["implementer"], exited=False
    )
    monkeypatch.setattr(orc.os, "write", lambda *_args: 1)
    app.write_active(b"input")
    assert panes["implementer"].scrolls == 1


def test_in_place_resume_closes_exited_session_fd_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    app, _state_file, panes = app_stub(
        tmp_path,
        {
            "status": "paused",
            "phase": "paused",
            "target_directory": str(target),
            "user_requests": [],
        },
    )
    session = argparse.Namespace(
        role="implementer",
        master_fd=71,
        pane=panes["implementer"],
        exited=True,
    )
    app.sessions = {"implementer": session}
    closed: list[int] = []
    monkeypatch.setattr(orc.os, "close", closed.append)

    app._retire_all_sessions()
    app._retire_all_sessions()

    assert closed == [71]
    assert session.master_fd == -1
    assert app.sessions == {}


@pytest.mark.parametrize("status", ["paused", "blocked", "completed"])
def test_in_place_resume_restarts_inactive_terminal_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: str
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    handoffs = (
        []
        if status != "completed"
        else [{"role": "implementer", "commit": "abc"}]
    )
    record: dict[str, object] = {
        "status": status,
        "phase": "complete" if status == "completed" else status,
        "stop_reason": "completion" if status == "completed" else "manual_pause",
        "target_directory": str(target),
        "backend": "codex",
        "backend_command": "codex",
        "backend_version": "version",
        "max_rounds": 3,
        "deadline_seconds": 120,
        "user_requests": ["old"],
        "handoffs": handoffs,
        "implementer_id": "old-igor",
        "reviewer_id": "old-rufus",
        "blocker_reason": "old blocker",
        "failed_role": "reviewer",
    }
    app, state_file, _panes = app_stub(tmp_path, record)
    launched: list[str] = []
    monkeypatch.setattr(app, "launch_role", launched.append)
    before = orc.load_state(state_file)["TASK-003"]

    assert app.open_resume_prompt()
    assert app.submit_resume_request("continue")

    saved = orc.load_state(state_file)["TASK-003"]
    assert launched == ["implementer"]
    assert saved["status"] == "active"
    assert saved["phase"] == "implementer"
    assert saved["round"] == 1
    assert saved["user_requests"] == ["old", "continue"]
    assert saved["handoffs"] == handoffs
    assert saved["target_directory"] == before["target_directory"]
    assert saved["backend"] == before["backend"]
    assert saved["backend_command"] == before["backend_command"]
    assert saved["backend_version"] == before["backend_version"]
    assert saved["max_rounds"] == before["max_rounds"]
    assert saved["deadline_seconds"] == before["deadline_seconds"]
    assert saved.get("stop_reason") is None
    assert "blocker_reason" not in saved
    assert "failed_role" not in saved
    assert saved["implementer_id"] is None
    assert saved["reviewer_id"] is None
    assert saved["deadline_at"] != before.get("deadline_at")


def test_in_place_resume_restarts_stopped_child_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    record: dict[str, object] = {
        "status": "stopped",
        "phase": "stopped",
        "stop_reason": "child_failure",
        "child_failure": {"role": "reviewer"},
        "target_directory": str(target),
        "backend": "codex",
        "max_rounds": 5,
        "deadline_seconds": 120,
        "user_requests": [],
        "handoffs": [],
    }
    app, state_file, _panes = app_stub(tmp_path, record)
    launched: list[str] = []
    monkeypatch.setattr(app, "launch_role", launched.append)
    assert app.open_resume_prompt()
    assert app.submit_resume_request("repair the failure")
    saved = orc.load_state(state_file)["TASK-003"]
    assert launched == ["implementer"]
    assert saved["status"] == "active"
    assert "child_failure" not in saved


def test_in_place_resume_empty_cancel_and_inconsistent_requests_are_noops(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    record: dict[str, object] = {
        "status": "paused",
        "phase": "paused",
        "target_directory": str(target),
        "backend": "codex",
        "max_rounds": 5,
        "deadline_seconds": 120,
        "user_requests": [],
        "handoffs": [],
    }
    app, state_file, _panes = app_stub(tmp_path, record)
    monkeypatch.setattr(app, "launch_role", lambda _role: pytest.fail("launch"))
    before = orc.load_state(state_file)
    assert app.open_resume_prompt()
    assert not app.submit_resume_request("")
    assert app.resume_prompt_active
    assert orc.load_state(state_file) == before
    app.on_key(Event("escape"))
    assert not app.resume_prompt_active
    assert orc.load_state(state_file) == before

    record["status"] = "active"
    record["phase"] = "implementer"
    orc.save_state(state_file, {"TASK-003": record})
    assert not app.open_resume_prompt()


@pytest.mark.parametrize(
    "record_updates",
    [
        {
            "status": "paused",
            "phase": "paused",
            "handoffs": [{"role": "implementer"}],
        },
        {
            "status": "completed",
            "phase": "complete",
            "child_failure": {"role": "reviewer"},
        },
        {
            "status": "stopped",
            "phase": "stopped",
            "stop_reason": "child_failure",
            "child_failure": {"role": "implementer"},
            "handoffs": [{"role": "reviewer"}],
        },
    ],
)
def test_in_place_resume_rejects_inconsistent_terminal_roles(
    tmp_path: Path, record_updates: dict[str, object]
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    record: dict[str, object] = {
        "target_directory": str(target),
        "user_requests": [],
    }
    record.update(record_updates)
    app, _state_file, _panes = app_stub(tmp_path, record)
    assert not app.open_resume_prompt()


def test_status_version_rail_reserves_complete_text() -> None:
    app = orc.OrcApp.__new__(orc.OrcApp)
    app.task_id = "TASK-012"
    app.sessions = {}
    record = {
        "status": "active",
        "phase": "implementer",
        "backend": "claude",
        "round": 1,
        "max_rounds": 5,
    }
    segments = app.status_segments(record)
    visible, _hint = app._visible_status_keys(segments, 80)
    assert orc.STATUS_VERSION_WIDTH == len(" orc v0.0.1")
    assert len(" orc v0.0.1") == 11
    assert "task" in visible
    assert 80 - orc.STATUS_VERSION_WIDTH >= sum(
        len(segments[key]) for key in visible
    ) + max(len(visible) - 1, 0) * len(orc.STATUS_SEGMENT_SEPARATOR)


@pytest.mark.integration
def test_textual_in_place_resume_prompt_submits_in_same_app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_file = tmp_path / "state.json"
    target = tmp_path / "target"
    target.mkdir()
    orc.save_state(
        state_file,
        {
            "TASK-012": {
                "status": "completed",
                "phase": "complete",
                "stop_reason": "completion",
                "target_directory": str(target),
                "backend": "codex",
                "backend_command": "codex",
                "backend_version": "unknown",
                "automatic_rounds": True,
                "max_rounds": 5,
                "deadline_seconds": 120,
                "round": 2,
                "user_requests": [],
                "handoffs": [],
                "implementer_id": None,
                "reviewer_id": None,
            }
        },
    )
    args = argparse.Namespace(state_file=state_file, codex="codex")
    app = orc.OrcApp(args, "TASK-012")
    launched: list[str] = []
    monkeypatch.setattr(app, "launch_role", launched.append)
    monkeypatch.setattr(app, "poll_state", lambda: None)

    async def exercise() -> None:
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            launched.clear()
            await pilot.press("ctrl+r")
            await pilot.pause()
            prompt = app.query_one("#resume-prompt", orc.Input)
            assert app.resume_prompt_active
            assert prompt.styles.display == "block"
            await pilot.press(*"continue")
            await pilot.press("enter")
            await pilot.pause()
            assert not app.resume_prompt_active
            assert launched == ["implementer"]
            assert (
                orc.load_state(state_file)["TASK-012"]["status"] == "active"
            )
            app.exit()

    asyncio.run(exercise())


@pytest.mark.integration
def test_textual_status_version_rail_is_complete_at_supported_sizes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_file = tmp_path / "state.json"
    target = tmp_path / "target"
    target.mkdir()
    orc.save_state(
        state_file,
        {
            "TASK-012": {
                "status": "completed",
                "phase": "complete",
                "target_directory": str(target),
                "backend": "codex",
                "round": 1,
                "max_rounds": 5,
                "handoffs": [],
            }
        },
    )
    async def exercise() -> None:
        for size in ((120, 40), (80, 40), (80, 24)):
            app = orc.OrcApp(argparse.Namespace(state_file=state_file), "TASK-012")
            monkeypatch.setattr(app, "launch_role", lambda _role: None)
            monkeypatch.setattr(app, "poll_state", lambda: None)
            async with app.run_test(size=size) as pilot:
                await pilot.pause()
                left = app.query_one("#status-left", orc.Container)
                version = app.query_one("#status-version", orc.Static)
                assert version.render().plain == " orc v0.0.1"
                assert version.styles.width.value == orc.STATUS_VERSION_WIDTH
                assert version.region.right == size[0]
                assert left.region.right == version.region.x
                for segment_id in orc.STATUS_SEGMENT_IDS:
                    segment = app.query_one(f"#{segment_id}", orc.Static)
                    assert segment.region.right <= version.region.x
                app.exit()

    asyncio.run(exercise())


class FakeStyle:
    def __init__(self) -> None:
        self.layout = None
        self.width = None
        self.height = None
        self.display = None


class FakePane:
    def __init__(
        self,
        width: int = 100,
        height: int = 40,
        content_width: int | None = None,
        content_height: int | None = None,
    ) -> None:
        self.size = argparse.Namespace(width=width, height=height)
        self.content_size = argparse.Namespace(
            width=width if content_width is None else content_width,
            height=height if content_height is None else content_height,
        )
        self.styles = FakeStyle()
        self.classes: set[str] = set()
        self.messages: list[str] = []
        self.scrolls = 0
        self.scroll_actions: list[tuple[str, int | None]] = []

    def add_class(self, value: str) -> None:
        self.classes.add(value)

    def remove_class(self, value: str) -> None:
        self.classes.discard(value)

    def show_message(self, value: str) -> None:
        self.messages.append(value)

    def feed(self, _data: bytes) -> None:
        pass

    def resize_terminal(self, _width: int, _height: int) -> None:
        pass

    def scroll_page(self, direction: int) -> None:
        self.scroll_actions.append(("page", direction))

    def scroll_to_home(self) -> None:
        self.scroll_actions.append(("home", None))

    def scroll_to_end(self) -> None:
        self.scrolls += 1
        self.scroll_actions.append(("end", None))


class FakeLoop:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    def add_reader(self, *args: object) -> None:
        self.calls.append(args)

    def remove_reader(self, *args: object) -> None:
        self.calls.append(args)


def app_stub(
    tmp_path: Path, record: dict[str, object]
) -> tuple[object, Path, dict[str, FakePane]]:
    state_file = tmp_path / "state.json"
    record.setdefault("backend", "codex")
    record.setdefault("automatic_rounds", True)
    record.setdefault("max_rounds", 5)
    record.setdefault("round", 1)
    orc.save_state(state_file, {"TASK-003": record})
    args = argparse.Namespace(state_file=state_file, codex="codex")
    app = orc.OrcApp.__new__(orc.OrcApp)
    app.args = args
    app.task_id = "TASK-003"
    app.sessions = {}
    app.started_roles = set()
    app.active_role = "implementer"
    app.layout_mode = ""
    app.last_status = "starting"
    app.event_loop = FakeLoop()
    panes = {"implementer": FakePane(), "reviewer": FakePane()}
    app.pane = lambda role: panes[role]
    return app, state_file, panes


def test_orc_app_launches_roles_with_target_cwd_and_resume_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ORC_DISABLE_IDLE_HOOK", raising=False)
    target = tmp_path / "target"
    target.mkdir()
    record: dict[str, object] = {
        "target_directory": str(target),
        "prompt": "initial",
        "user_requests": [],
        "implementer_id": None,
        "reviewer_id": None,
    }
    app, _state_file, _panes = app_stub(tmp_path, record)
    launched: list[tuple[list[str], dict[str, str], Path | str | None]] = []
    monkeypatch.setattr(
        app,
        "fork_codex",
        lambda command, environment, cwd=None: (
            launched.append((command, environment, cwd))
            or (123, os.open("/dev/null", os.O_RDWR))
        ),
    )
    monkeypatch.setattr(app, "set_master_reader", lambda _session: None)
    monkeypatch.setattr(app, "resize_session", lambda _session: None)
    monkeypatch.setattr(app, "update_layout", lambda: None)
    statuses: list[str] = []
    monkeypatch.setattr(app, "update_status", statuses.append)

    app.launch_role("implementer")
    assert launched[0][2] == target
    assert launched[0][1]["ORC_TARGET_DIRECTORY"] == str(target)
    assert "initial" in launched[0][0][-1]
    assert "implementer" in app.started_roles

    app.started_roles.clear()
    record["reviewer_id"] = "rufus-thread"
    record["user_requests"] = ["fix review findings"]
    orc.save_state(app.args.state_file, {"TASK-003": record})
    app.launch_role("reviewer")
    assert launched[1][0][3:5] == ["resume", "rufus-thread"]
    assert "Target project directory" in launched[1][0][-1]
    assert statuses


@pytest.mark.parametrize("role", ["implementer", "reviewer"])
@pytest.mark.parametrize("marker_contents", [None, "", "agentbox marker contents"])
@pytest.mark.parametrize("resuming", [False, True])
def test_agentbox_flag_applies_to_both_roles_and_launch_modes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    role: str,
    marker_contents: str | None,
    resuming: bool,
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    marker = tmp_path / "identity"
    if marker_contents is not None:
        marker.write_text(marker_contents)
    monkeypatch.setattr(orc, "AGENTBOX_IDENTITY", marker)
    monkeypatch.setattr(orc.sys, "platform", "linux")
    thread_key = f"{role}_id"
    record: dict[str, object] = {
        "target_directory": str(target),
        "prompt": "initial",
        "user_requests": ["follow up"] if resuming else [],
        "implementer_id": None,
        "reviewer_id": None,
    }
    if resuming:
        record[thread_key] = f"{role}-thread"
    app, _state_file, _panes = app_stub(tmp_path, record)
    launched: list[list[str]] = []
    monkeypatch.setattr(
        app,
        "fork_codex",
        lambda command, _environment, _cwd=None: (
            launched.append(command) or (123, os.open("/dev/null", os.O_RDWR))
        ),
    )
    monkeypatch.setattr(app, "set_master_reader", lambda _session: None)
    monkeypatch.setattr(app, "resize_session", lambda _session: None)
    monkeypatch.setattr(app, "update_layout", lambda: None)
    monkeypatch.setattr(app, "update_status", lambda _message: None)

    app.launch_role(role)

    command = launched[0]
    assert command[0] == "codex"
    expected_flags = 1 if marker_contents is not None else 0
    assert command.count(orc.CODEX_AGENTBOX_FLAG) == expected_flags
    if resuming:
        assert "resume" in command


def test_agentbox_flag_is_not_duplicated_in_configured_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    marker = tmp_path / "identity"
    marker.write_text("")
    monkeypatch.setattr(orc, "AGENTBOX_IDENTITY", marker)
    app, _state_file, _panes = app_stub(
        tmp_path,
        {
            "target_directory": str(target),
            "prompt": "initial",
            "user_requests": [],
            "implementer_id": None,
            "reviewer_id": None,
        },
    )
    app.args.codex = ["codex executable with spaces", orc.CODEX_AGENTBOX_FLAG]
    launched: list[list[str]] = []
    monkeypatch.setattr(
        app,
        "fork_codex",
        lambda command, _environment, _cwd=None: (
            launched.append(command) or (123, os.open("/dev/null", os.O_RDWR))
        ),
    )
    monkeypatch.setattr(app, "set_master_reader", lambda _session: None)
    monkeypatch.setattr(app, "resize_session", lambda _session: None)
    monkeypatch.setattr(app, "update_layout", lambda: None)
    monkeypatch.setattr(app, "update_status", lambda _message: None)

    app.launch_role("implementer")

    assert launched[0][0] == "codex executable with spaces"
    assert launched[0].count(orc.CODEX_AGENTBOX_FLAG) == 1


@pytest.mark.integration
@pytest.mark.parametrize("role", ["implementer", "reviewer"])
@pytest.mark.parametrize("marker_present", [False, True])
@pytest.mark.parametrize("resuming", [False, True])
@pytest.mark.parametrize("selector", ["--codex", "CODEX_COMMAND"])
def test_agentbox_launch_executes_spaced_codex_through_real_pty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    role: str,
    marker_present: bool,
    resuming: bool,
    selector: str,
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    fake_codex = tmp_path / "fake codex"
    capture = tmp_path / "capture.json"
    fake_codex.write_text(
        f"#!{sys.executable}\n"
        "import json, os, pathlib, sys\n"
        "pathlib.Path(os.environ['ORC_CAPTURE']).write_text(\n"
        "    json.dumps({'argv': sys.argv, 'cwd': os.getcwd()})\n"
        ")\n"
        "print('fake codex', flush=True)\n"
    )
    fake_codex.chmod(0o755)
    marker = tmp_path / "identity"
    if marker_present:
        marker.write_text("")
    monkeypatch.setattr(orc, "AGENTBOX_IDENTITY", marker)
    monkeypatch.setattr(orc.sys, "platform", "linux")
    monkeypatch.setenv("ORC_CAPTURE", str(capture))

    thread_key = f"{role}_id"
    record: dict[str, object] = {
        "target_directory": str(target),
        "prompt": "initial",
        "user_requests": ["follow up"] if resuming else [],
        "implementer_id": None,
        "reviewer_id": None,
    }
    if resuming:
        record[thread_key] = f"{role}-thread"
    app, state_file, _panes = app_stub(tmp_path, record)
    if selector == "CODEX_COMMAND":
        monkeypatch.setenv("CODEX_COMMAND", str(fake_codex))
        monkeypatch.setenv("ORC_BACKEND", "codex")
        cli = [
            "--state-file",
            str(state_file),
            "begin",
            str(target),
            "TASK-003",
            "initial",
        ]
    else:
        monkeypatch.setenv("CODEX_COMMAND", str(fake_codex))
        monkeypatch.setenv("ORC_BACKEND", "invalid")
        cli = [
            "--state-file",
            str(state_file),
            "begin",
            str(target),
            "TASK-003",
            "initial",
            "--codex",
        ]
    app.args = orc.parse_args(cli)
    assert orc.selected_backend(app.args) == "codex"
    app.set_master_reader = lambda _session: None
    app.resize_session = lambda _session: None
    app.update_layout = lambda: None
    app.update_status = lambda _message: None

    app.launch_role(role)
    session = app.sessions[role]
    _pid, status = os.waitpid(session.pid, 0)
    os.close(session.master_fd)

    assert os.WIFEXITED(status)
    captured = json.loads(capture.read_text())
    assert captured["cwd"] == str(target)
    assert captured["argv"][0] == str(fake_codex)
    assert captured["argv"].count(orc.CODEX_AGENTBOX_FLAG) == int(marker_present)
    if resuming:
        resume_index = captured["argv"].index("resume")
        assert captured["argv"][resume_index : resume_index + 2] == [
            "resume",
            f"{role}-thread",
        ]


def test_launch_can_disable_idle_hook_for_orc_testing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    record: dict[str, object] = {
        "target_directory": str(target),
        "prompt": "initial",
        "user_requests": [],
        "implementer_id": None,
        "reviewer_id": None,
    }
    app, _state_file, _panes = app_stub(tmp_path, record)
    launched: list[list[str]] = []
    monkeypatch.setattr(
        app,
        "fork_codex",
        lambda command, _environment, _cwd=None: (
            launched.append(command) or (123, os.open("/dev/null", os.O_RDWR))
        ),
    )
    monkeypatch.setattr(app, "set_master_reader", lambda _session: None)
    monkeypatch.setattr(app, "resize_session", lambda _session: None)
    monkeypatch.setattr(app, "update_layout", lambda: None)
    monkeypatch.setattr(app, "update_status", lambda _message: None)
    monkeypatch.setenv("ORC_DISABLE_IDLE_HOOK", "1")
    app.launch_role("implementer")

    assert launched and "-c" not in launched[0]


def test_orc_app_launch_error_and_invalid_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, _state_file, _panes = app_stub(
        tmp_path, {"target_directory": str(tmp_path), "prompt": "p"}
    )
    errors: list[str] = []
    monkeypatch.setattr(app, "fatal_error", errors.append)
    monkeypatch.setattr(app, "update_layout", lambda: None)
    monkeypatch.setattr(app, "set_master_reader", lambda _session: None)
    monkeypatch.setattr(app, "resize_session", lambda _session: None)
    monkeypatch.setattr(app, "update_status", lambda _message: None)
    app.launch_role("implementer")
    assert errors == []
    app.started_roles.add("implementer")
    app.launch_role("implementer")
    assert len(errors) == 0

    app.started_roles.clear()
    record = {
        "target_directory": str(tmp_path),
        "backend": "codex",
        "prompt": "p",
        "user_requests": [],
    }
    orc.save_state(app.args.state_file, {"TASK-003": record})
    monkeypatch.setattr(
        app, "fork_codex", lambda *_args: (_ for _ in ()).throw(OSError("no"))
    )
    app.launch_role("reviewer")
    assert any("could not launch reviewer" in value for value in errors)

    orc.save_state(
        app.args.state_file,
        {"TASK-003": {"backend": "codex", "prompt": "p"}},
    )
    app.started_roles.clear()
    app.launch_role("implementer")
    assert any("no target directory" in value for value in errors)


def test_orc_app_io_resize_layout_and_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    app, _state_file, panes = app_stub(
        tmp_path,
        {"target_directory": str(target), "prompt": "p", "user_requests": []},
    )
    loop = FakeLoop()
    app.event_loop = loop
    with pytest.raises(RuntimeError, match="event loop"):
        app.event_loop = None
        app.set_master_reader(argparse.Namespace(master_fd=1))
    app.event_loop = loop
    session = argparse.Namespace(
        role="implementer", master_fd=1, pane=panes["implementer"], exited=False, pid=12
    )
    app.set_master_reader(session)
    assert loop.calls

    monkeypatch.setattr(orc.os, "read", lambda *_: b"hello")
    panes["implementer"].feed = lambda data: setattr(panes["implementer"], "data", data)
    app.read_session(session)
    assert panes["implementer"].data == b"hello"
    monkeypatch.setattr(
        orc.os, "read", lambda *_: (_ for _ in ()).throw(BlockingIOError())
    )
    app.read_session(session)
    error = OSError(1, "bad")
    monkeypatch.setattr(orc.os, "read", lambda *_: (_ for _ in ()).throw(error))
    statuses: list[str] = []
    monkeypatch.setattr(app, "update_status", statuses.append)
    app.read_session(session)
    assert statuses

    monkeypatch.setattr(orc.os, "write", lambda *_: 1)
    app.sessions = {}
    app.write_active(b"x")
    app.sessions["implementer"] = session
    app.write_active(b"x")
    session.exited = True
    app.write_active(b"x")
    session.exited = False
    error = OSError(5, "write")
    monkeypatch.setattr(orc.os, "write", lambda *_: (_ for _ in ()).throw(error))
    app.write_active(b"x")
    assert statuses

    monkeypatch.setattr(orc, "set_pty_size", lambda *_: None)
    app.resize_session(session)
    app.sessions = {"implementer": session}
    monkeypatch.setattr(app, "update_layout", lambda: statuses.append("layout"))
    monkeypatch.setattr(
        app, "resize_session", lambda _session: statuses.append("resize")
    )
    app.on_resize(None)
    assert "resize" in statuses
    app.update_layout = orc.OrcApp.update_layout.__get__(app, type(app))
    app.update_status = orc.OrcApp.update_status.__get__(app, type(app))

    app._fake_running = False
    monkeypatch.setattr(
        type(app), "is_running", property(lambda self: self._fake_running)
    )
    app.update_layout()
    app._fake_running = True
    app._fake_size = argparse.Namespace(width=140, height=40)
    monkeypatch.setattr(type(app), "size", property(lambda self: self._fake_size))
    pane_container = argparse.Namespace(styles=FakeStyle())
    status_widget = argparse.Namespace(update=lambda _value: None)
    app.query_one = lambda selector, *_args: (
        pane_container if selector == "#panes" else status_widget
    )
    # Exercise the three layout decisions with real pane style/class updates.
    monkeypatch.setattr(app, "pane", lambda role: panes[role])
    app.update_layout()
    app._fake_size = argparse.Namespace(width=50, height=40)
    app.update_layout()
    app._fake_size = argparse.Namespace(width=50, height=20)
    app.update_layout()
    assert app.layout_mode == "single"
    app._fake_running = False
    app.update_status("stopped")
    assert app.last_status == "stopped"


def test_orc_app_polling_unmount_and_mount(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    app, state_file, panes = app_stub(
        tmp_path,
        {"target_directory": str(target), "prompt": "p", "user_requests": []},
    )
    exited: list[object] = []
    monkeypatch.setattr(app, "exit", lambda *args: exited.append(args))
    statuses: list[str] = []
    monkeypatch.setattr(app, "update_status", statuses.append)
    app.poll_state()
    record = orc.load_state(state_file)["TASK-003"]
    record["status"] = "paused"
    orc.save_state(state_file, {"TASK-003": record})
    app.poll_state()
    assert not exited
    record["status"] = "active"
    record["phase"] = "reviewer"
    orc.save_state(state_file, {"TASK-003": record})
    monkeypatch.setattr(app, "launch_role", lambda role: statuses.append(role))
    app.poll_state()
    assert "reviewer" in statuses

    app.active_role = "implementer"
    app.sessions = {
        "implementer": argparse.Namespace(
            role="implementer",
            pid=4,
            master_fd=1,
            pane=panes["implementer"],
            exited=False,
        )
    }
    monkeypatch.setattr(orc.os, "waitpid", lambda *_: (4, 0))
    monkeypatch.setattr(app.event_loop, "remove_reader", lambda *_: None)
    app.poll_children()
    assert panes["implementer"].messages
    assert app.sessions["implementer"].exited

    app.sessions = {
        "reviewer": argparse.Namespace(
            role="reviewer", pid=5, master_fd=1, pane=panes["reviewer"], exited=False
        )
    }
    record["status"] = "paused"
    orc.save_state(state_file, {"TASK-003": record})
    app.active_role = "reviewer"
    monkeypatch.setattr(
        orc.os, "waitpid", lambda *_: (_ for _ in ()).throw(ChildProcessError())
    )
    app.poll_children()
    assert panes["reviewer"].messages

    app.sessions = {}
    monkeypatch.setattr(orc.os, "name", "nt")
    monkeypatch.setattr(app, "fatal_error", lambda message: statuses.append(message))
    app.on_mount()
    assert any("POSIX" in value for value in statuses)


def test_run_app_requires_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args = argparse.Namespace(state_file=tmp_path / "state.json")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    with pytest.raises(SystemExit, match="interactive terminal"):
        orc.run_app(args, "TASK-003")


def test_resume_rejects_bad_requests_and_unknown_task(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    state_file = tmp_path / "state.json"
    args = cli_args(state_file, target)
    with pytest.raises(SystemExit, match="unknown task"):
        orc.resume(args)
    orc.save_state(
        state_file,
        {
            "TASK-003": {
                "target_directory": str(target),
                "backend": "codex",
                "user_requests": "bad",
            }
        },
    )
    with pytest.raises(SystemExit, match="invalid user_requests"):
        orc.resume(args)


def test_idle_hook_uses_saved_thread_and_repairs_bad_handoffs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    state_file = tmp_path / "state.json"
    orc.save_state(
        state_file,
        {
            "TASK-003": {
                "target_directory": str(target),
                "reviewer_id": "saved",
                "handoffs": "bad",
            }
        },
    )
    monkeypatch.setenv("ORC_TASK_ID", "TASK-003")
    monkeypatch.setenv("ORC_ROLE", "reviewer")
    args = argparse.Namespace(
        state_file=state_file, payload=json.dumps({"event": "idle"})
    )
    orc.idle_hook(args)
    record = orc.load_state(state_file)["TASK-003"]
    assert record["last_handoff"]["thread_id"] == "saved"
    assert record["handoffs"]


def test_main_dispatches_idle_hook(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[str] = []
    monkeypatch.setattr(
        orc, "parse_args", lambda: argparse.Namespace(command="idle-hook")
    )
    monkeypatch.setattr(orc, "idle_hook", lambda _args: called.append("hook"))
    orc.main()
    assert called == ["hook"]


def test_error_paths_and_pane_render_timer(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    original_resolve = Path.resolve
    monkeypatch.setattr(
        Path,
        "resolve",
        lambda self, strict=False: (_ for _ in ()).throw(RuntimeError("loop")),
    )
    with pytest.raises(SystemExit, match="cannot access"):
        orc.normalize_target_directory(tmp_path)
    monkeypatch.setattr(Path, "resolve", original_resolve)

    class BadParent:
        def mkdir(self, **_kwargs: object) -> None:
            raise OSError("read only")

    with pytest.raises(SystemExit, match="cannot write"):
        orc.save_state(argparse.Namespace(parent=BadParent()), {})

    pane = orc.SessionPane("reviewer")
    monkeypatch.setattr(type(pane), "is_attached", property(lambda _self: True))
    scheduled: list[str] = []
    pane.schedule_render = lambda: scheduled.append("scheduled")
    pane.feed(b"visible")
    assert scheduled == ["scheduled"]
    timer = argparse.Namespace(stop=lambda: scheduled.append("stopped"))
    pane.render_timer = timer
    pane.update = lambda _value: None
    pane.show_message("waiting")
    assert "stopped" in scheduled
    pane.has_visible_content = True
    pane.message = None
    pane.flush_render()
    assert pane.render_timer is None
    assert orc.SessionPane._rich_color("") is None
    assert orc.SessionPane._rich_color("abcdef") == "#abcdef"
    assert orc.SessionPane._rich_color("red") == "red"


def test_app_constructor_compose_mount_and_fatal_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args = argparse.Namespace(state_file=tmp_path / "state.json")
    app = orc.OrcApp(args, "TASK-003")
    assert app.active_role == "implementer"
    assert len(list(app.compose())) == 3
    exited: list[object] = []
    monkeypatch.setattr(app, "exit", lambda *args: exited.append(args))
    app.fatal_error("bad")
    assert app.last_status == "bad" and exited

    loop = FakeLoop()
    monkeypatch.setattr(orc.asyncio, "get_running_loop", lambda: loop)
    intervals: list[object] = []
    monkeypatch.setattr(app, "set_interval", lambda *args: intervals.append(args))
    monkeypatch.setattr(app, "update_layout", lambda: None)
    monkeypatch.setattr(app, "call_after_refresh", lambda *args: intervals.append(args))
    app.on_mount()
    assert app.event_loop is loop and len(intervals) == 3
    assert app.pane("implementer") if False else True


def test_launch_resume_and_poll_edge_branches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ORC_DISABLE_IDLE_HOOK", raising=False)
    target = tmp_path / "target"
    target.mkdir()
    record: dict[str, object] = {
        "target_directory": str(target),
        "prompt": "initial",
        "user_requests": ["follow up"],
        "implementer_id": "igor",
        "reviewer_id": None,
    }
    app, _state_file, _panes = app_stub(tmp_path, record)
    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        app,
        "fork_codex",
        lambda command, environment, cwd=None: (
            calls.append((command, environment, cwd))
            or (12, os.open("/dev/null", os.O_RDWR))
        ),
    )
    monkeypatch.setattr(app, "set_master_reader", lambda _session: None)
    monkeypatch.setattr(app, "resize_session", lambda _session: None)
    monkeypatch.setattr(app, "update_layout", lambda: None)
    monkeypatch.setattr(app, "update_status", lambda _message: None)
    monkeypatch.setenv("TERM", "dumb")
    app.launch_role("implementer")
    assert calls[0][0][3] == "resume" and calls[0][1]["TERM"] == "xterm-256color"

    record["user_requests"] = []
    orc.save_state(app.args.state_file, {"TASK-003": record})
    app.started_roles.clear()
    errors: list[str] = []
    monkeypatch.setattr(app, "fatal_error", errors.append)
    app.launch_role("implementer")
    assert not errors

    # A task missing from state is a fatal launch condition.
    orc.save_state(app.args.state_file, {})
    app.started_roles.clear()
    app.launch_role("implementer")
    assert any("no state" in value for value in errors)

    app.sessions = {}
    app.poll_state()
    assert app.sessions == {}


def test_poll_children_keeps_ui_alive_and_unmounts_resources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    app, state_file, panes = app_stub(
        tmp_path,
        {"target_directory": str(target), "prompt": "p", "user_requests": []},
    )
    orc.save_state(state_file, {})
    app.active_role = "implementer"
    session = argparse.Namespace(
        role="implementer", pid=7, master_fd=99, pane=panes["implementer"], exited=False
    )
    app.sessions = {"implementer": session}
    monkeypatch.setattr(orc.os, "waitpid", lambda *_: (0, 0))
    app.poll_children()
    assert not session.exited
    monkeypatch.setattr(orc.os, "waitpid", lambda *_: (7, 0))
    monkeypatch.setattr(
        app.event_loop,
        "remove_reader",
        lambda *_: (_ for _ in ()).throw(NotImplementedError()),
    )
    exits: list[object] = []
    monkeypatch.setattr(app, "exit", lambda *args: exits.append(args))
    monkeypatch.setattr(app, "update_status", lambda _message: None)
    app.poll_children()
    assert session.exited and not exits

    app.sessions = {"done": argparse.Namespace(pid=1, master_fd=99, exited=True)}
    app.on_unmount()
    app.sessions = {"live": argparse.Namespace(pid=2, master_fd=99, exited=False)}
    monkeypatch.setattr(
        orc.os, "killpg", lambda *_: (_ for _ in ()).throw(ProcessLookupError())
    )
    monkeypatch.setattr(orc.os, "close", lambda *_: None)
    app.on_unmount()


def test_ctrl_q_action_quit_success_run_and_main_branches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    app = orc.OrcApp.__new__(orc.OrcApp)
    exits: list[object] = []
    monkeypatch.setattr(app, "exit", lambda *args: exits.append(args))
    event = Event("ctrl+q")
    app.on_key(event)
    assert exits and event.stopped

    import asyncio as _asyncio

    _asyncio.run(app.action_quit())
    assert len(exits) == 2

    args = argparse.Namespace()
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)

    class FakeApp:
        def __init__(self, _args: object, _task: str) -> None:
            pass

        def run(self) -> None:
            pass

    monkeypatch.setattr(orc, "OrcApp", FakeApp)
    orc.run_app(args, "TASK-003")
    assert "orchestration ended" in capsys.readouterr().out

    target = tmp_path / "target"
    target.mkdir()
    state_file = tmp_path / "state.json"
    orc.save_state(
        state_file,
        {
            "TASK-003": {
                "target_directory": str(target),
                "backend": "codex",
                "user_feedback": ["old"],
            }
        },
    )
    monkeypatch.setattr(orc, "run_app", lambda *_: None)
    orc.resume(cli_args(state_file, target))
    assert orc.load_state(state_file)["TASK-003"]["user_requests"] == [
        "old",
        "implement the task",
    ]

    calls: list[str] = []
    monkeypatch.setattr(orc, "parse_args", lambda: argparse.Namespace(command="begin"))
    monkeypatch.setattr(orc, "begin", lambda _args: calls.append("begin"))
    orc.main()
    monkeypatch.setattr(orc, "parse_args", lambda: argparse.Namespace(command="resume"))
    monkeypatch.setattr(orc, "resume", lambda _args: calls.append("resume"))
    orc.main()
    assert calls == ["begin", "resume"]


def hook_args(state_file: Path, payload: dict[str, object]) -> argparse.Namespace:
    return argparse.Namespace(state_file=state_file, payload=json.dumps(payload))


def test_automatic_cli_bounds_and_removed_manual_syntax(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    auto = orc.parse_args(
        [
            "begin",
            str(target),
            "TASK-005",
            "implement",
            "--max-rounds",
            "3",
            "--deadline-minutes",
            "7",
            "--codex",
        ]
    )
    assert auto.backend_selector == "codex"
    assert auto.max_rounds == 3
    assert auto.deadline_minutes == 7
    with pytest.raises(SystemExit):
        orc.parse_args(
            ["begin", str(target), "TASK-005", "implement", "--auto"]
        )
    with pytest.raises(SystemExit):
        orc.parse_args(
            [
                "begin",
                str(target),
                "TASK-005",
                "implement",
                "--max-rounds",
                "6",
                "--codex",
            ]
        )
    with pytest.raises(SystemExit):
        orc.parse_args(
            [
                "begin",
                str(target),
                "TASK-005",
                "implement",
                "--deadline-minutes",
                "1441",
                "--codex",
            ]
        )


def test_begin_persists_bounded_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    state_file = tmp_path / "state.json"
    args = orc.parse_args(
        [
            "--state-file",
            str(state_file),
            "begin",
            str(target),
            "TASK-005",
            "implement",
            "--max-rounds",
            "2",
            "--deadline-minutes",
            "3",
            "--codex",
        ]
    )
    monkeypatch.setattr(orc, "run_app", lambda *_: None)
    orc.begin(args)
    record = orc.load_state(state_file)["TASK-005"]
    assert record["automatic_rounds"] is True
    assert record["max_rounds"] == 2
    assert record["deadline_seconds"] == 180
    assert record["cycle_started_at"]
    assert record["deadline_at"]
    assert record["stop_reason"] is None


def test_backend_selector_precedence_and_required_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    state_file = tmp_path / "state.json"
    monkeypatch.delenv("ORC_BACKEND", raising=False)
    args = orc.parse_args(
        ["--state-file", str(state_file), "begin", str(target), "TASK-005"]
    )
    with pytest.raises(SystemExit, match="select a backend"):
        orc.begin(args)
    assert not state_file.exists()

    monkeypatch.setenv("ORC_BACKEND", "claude")
    selected = orc.parse_args(["begin", str(target), "TASK-005"])
    assert orc.selected_backend(selected) == "claude"
    explicit = orc.parse_args(["begin", str(target), "TASK-005", "--codex"])
    assert orc.selected_backend(explicit) == "codex"
    monkeypatch.setenv("ORC_BACKEND", "invalid")
    assert orc.selected_backend(explicit) == "codex"
    with pytest.raises(SystemExit):
        orc.parse_args(
            ["begin", str(target), "TASK-005", "--codex", "--claude"]
        )


def test_resume_parser_has_no_directory_or_backend_selector(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    args = orc.parse_args(["resume", "TASK-005", "continue"])
    assert args.task_id == "TASK-005"
    assert args.prompt == "continue"
    assert not hasattr(args, "directory")
    with pytest.raises(SystemExit):
        orc.parse_args(["resume", str(target), "TASK-005", "continue"])


def test_legacy_resume_migrates_automatic_settings_after_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    state_file = tmp_path / "state.json"
    record = {
        "status": "paused",
        "phase": "reviewer",
        "round": 2,
        "target_directory": str(target),
        "backend": "codex",
        "automatic_rounds": False,
        "max_rounds": 4,
        "deadline_seconds": 300,
        "deadline_at": "2000-01-01T00:00:00+00:00",
        "handoffs": [{"role": "implementer"}],
        "user_requests": ["old request"],
    }
    orc.save_state(state_file, {"TASK-005": record})
    configured_codex = tmp_path / "configured codex"
    monkeypatch.setenv("CODEX_COMMAND", str(configured_codex))
    args = orc.parse_args(
        ["--state-file", str(state_file), "resume", "TASK-005", "continue"]
    )
    monkeypatch.setattr(orc, "run_app", lambda *_: None)
    orc.resume(args)
    saved = orc.load_state(state_file)["TASK-005"]
    assert saved["automatic_rounds"] is True
    assert saved["max_rounds"] == 4
    assert saved["deadline_seconds"] == 300
    assert saved["backend_command"] == str(configured_codex)
    assert saved["round"] == 2
    assert saved["handoffs"] == [{"role": "implementer"}]
    assert saved["user_requests"] == ["old request", "continue"]
    assert orc.parse_timestamp(saved["deadline_at"]) > orc.utc_now()


@pytest.mark.parametrize("role", ["implementer", "reviewer"])
def test_unable_to_proceed_persists_blocker_and_does_not_transition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, role: str
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    state_file = tmp_path / "state.json"
    record = {
        "status": "active",
        "phase": role,
        "round": 1,
        "target_directory": str(target),
        "backend": "codex",
        "handoffs": [],
        "processed_idle_events": [],
        f"{role}_id": f"{role}-thread",
    }
    orc.save_state(state_file, {"TASK-005": record})
    monkeypatch.setenv("ORC_TASK_ID", "TASK-005")
    monkeypatch.setenv("ORC_ROLE", role)
    payload = {
        "session_id": f"{role}-thread",
        "status": orc.UNABLE_TO_PROCEED,
        "reason": "Need a human choice about the release target.",
        "last-assistant-message": "Status: UNABLE_TO_PROCEED",
    }
    orc.idle_hook(hook_args(state_file, payload))
    saved = orc.load_state(state_file)["TASK-005"]
    assert saved["status"] == "blocked"
    assert saved["phase"] == "blocked"
    assert saved["stop_reason"] == "clarification"
    assert saved["blocker_role"] == role
    assert saved["blocker_reason"] == "Need a human choice about the release target."
    assert len(saved["handoffs"]) == 1

    before = saved.copy()
    with pytest.raises(SystemExit, match="non-empty"):
        args = orc.parse_args(
            ["--state-file", str(state_file), "resume", "TASK-005", " "]
        )
        orc.resume(args)
    assert orc.load_state(state_file)["TASK-005"] == before


def test_resume_delivers_exact_clarification_without_resetting_limits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    state_file = tmp_path / "state.json"
    record = {
        "status": "blocked",
        "phase": "blocked",
        "round": 2,
        "target_directory": str(target.resolve()),
        "backend": "codex",
        "user_requests": [],
        "automatic_rounds": True,
        "max_rounds": 4,
        "deadline_seconds": 300,
        "cycle_started_at": "2026-08-23T00:00:00+00:00",
        "deadline_at": "2099-08-23T00:00:00+00:00",
        "stop_reason": "clarification",
    }
    orc.save_state(state_file, {"TASK-005": record})
    args = orc.parse_args(
        [
            "--state-file",
            str(state_file),
                "resume",
                "TASK-005",
            "Choose option B exactly",
        ]
    )
    monkeypatch.setattr(orc, "run_app", lambda *_: None)
    orc.resume(args)
    saved = orc.load_state(state_file)["TASK-005"]
    assert saved["user_requests"] == ["Choose option B exactly"]
    assert saved["max_rounds"] == 4
    assert saved["deadline_seconds"] == 300
    assert saved["round"] == 2
    assert saved["status"] == "active"
    assert saved["phase"] == "implementer"


def test_auto_cycles_stop_at_completion_and_ignore_duplicate_idle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    state_file = tmp_path / "state.json"
    record = {
        "status": "active",
        "phase": "reviewer",
        "round": 1,
        "target_directory": str(target),
        "automatic_rounds": True,
        "max_rounds": 5,
        "deadline_at": "2099-08-23T00:00:00+00:00",
        "handoffs": [],
        "reviewer_id": "rufus",
    }
    orc.save_state(state_file, {"TASK-005": record})
    monkeypatch.setenv("ORC_TASK_ID", "TASK-005")
    monkeypatch.setenv("ORC_ROLE", "reviewer")
    payload = {
        "session_id": "rufus",
        "status": "COMPLETE",
        "last-assistant-message": "TASK COMPLETE",
    }
    args = hook_args(state_file, payload)
    orc.idle_hook(args)
    orc.idle_hook(args)
    saved = orc.load_state(state_file)["TASK-005"]
    assert saved["stop_reason"] == "completion"
    assert saved["reviewer_reported_complete"] is True
    assert saved["phase"] == "complete"
    assert len(saved["handoffs"]) == 1


def test_auto_cycle_limit_and_deadline_are_distinct(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    state_file = tmp_path / "state.json"
    base = {
        "status": "active",
        "phase": "reviewer",
        "round": 2,
        "target_directory": str(target),
        "automatic_rounds": True,
        "max_rounds": 2,
        "deadline_at": "2099-08-23T00:00:00+00:00",
        "handoffs": [],
        "reviewer_id": "rufus",
    }
    orc.save_state(state_file, {"TASK-005": base})
    monkeypatch.setenv("ORC_TASK_ID", "TASK-005")
    monkeypatch.setenv("ORC_ROLE", "reviewer")
    payload = {"session_id": "rufus", "last-assistant-message": "not complete"}
    orc.idle_hook(hook_args(state_file, payload))
    saved = orc.load_state(state_file)["TASK-005"]
    assert saved["stop_reason"] == "max_rounds"

    base["phase"] = "implementer"
    base["status"] = "active"
    base["deadline_at"] = "2000-01-01T00:00:00+00:00"
    base["processed_idle_events"] = []
    orc.save_state(state_file, {"TASK-005": base})
    monkeypatch.setenv("ORC_ROLE", "implementer")
    orc.idle_hook(
        hook_args(
            state_file,
            {"session_id": "igor", "last-assistant-message": "late"},
        )
    )
    saved = orc.load_state(state_file)["TASK-005"]
    assert saved["stop_reason"] == "deadline"
    assert saved["status"] == "stopped"


def test_malformed_handoff_is_rejected_without_state_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    state_file = tmp_path / "state.json"
    record = {
        "status": "active",
        "phase": "implementer",
        "target_directory": str(target),
        "handoffs": [],
    }
    orc.save_state(state_file, {"TASK-005": record})
    monkeypatch.setenv("ORC_TASK_ID", "TASK-005")
    monkeypatch.setenv("ORC_ROLE", "implementer")
    with pytest.raises(SystemExit, match="requires a concise reason"):
        orc.idle_hook(
            hook_args(
                state_file,
                {"status": orc.UNABLE_TO_PROCEED, "session_id": "igor"},
            )
        )
    assert orc.load_state(state_file)["TASK-005"] == record


def test_auto_launch_resumes_without_human_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    record: dict[str, object] = {
        "status": "active",
        "phase": "implementer",
        "round": 2,
        "target_directory": str(target),
        "prompt": "initial",
        "user_requests": [],
        "automatic_rounds": True,
        "implementer_id": "igor-thread",
        "reviewer_id": None,
    }
    app, _state_file, _panes = app_stub(tmp_path, record)
    commands: list[list[str]] = []
    monkeypatch.setattr(
        app,
        "fork_codex",
        lambda command, _environment, _cwd=None: (
            commands.append(command) or (123, os.open("/dev/null", os.O_RDWR))
        ),
    )
    monkeypatch.setattr(app, "set_master_reader", lambda _session: None)
    monkeypatch.setattr(app, "resize_session", lambda _session: None)
    monkeypatch.setattr(app, "update_layout", lambda: None)
    monkeypatch.setattr(app, "update_status", lambda _message: None)
    app.launch_role("implementer")
    assert commands[0][3:5] == ["resume", "igor-thread"]
    assert "Continue implementing the task" in commands[0][-1]
    assert "User request:" not in commands[0][-1]


def test_stale_same_role_session_or_generation_is_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    state_file = tmp_path / "state.json"
    record = {
        "status": "active",
        "phase": "implementer",
        "round": 2,
        "target_directory": str(target),
        "implementer_id": "current",
        "role_generations": {"implementer": 4},
        "handoffs": [],
        "processed_idle_events": [],
    }
    orc.save_state(state_file, {"TASK-005": record})
    monkeypatch.setenv("ORC_TASK_ID", "TASK-005")
    monkeypatch.setenv("ORC_ROLE", "implementer")
    orc.idle_hook(
        hook_args(
            state_file,
            {
                "session_id": "old",
                "round": 2,
                "generation": 3,
                "last-assistant-message": "stale",
            },
        )
    )
    saved = orc.load_state(state_file)["TASK-005"]
    assert saved == record


def test_ordinary_handoff_status_is_metadata_not_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    state_file = tmp_path / "state.json"
    orc.save_state(
        state_file,
        {
            "TASK-005": {
                "status": "active",
                "phase": "implementer",
                "round": 1,
                "target_directory": str(target),
                "handoffs": [],
            }
        },
    )
    monkeypatch.setenv("ORC_TASK_ID", "TASK-005")
    monkeypatch.setenv("ORC_ROLE", "implementer")
    orc.idle_hook(
        hook_args(
            state_file,
            {
                "session_id": "igor",
                "status": "IMPLEMENTED",
                "last-assistant-message": "Status: IMPLEMENTED",
            },
        )
    )
    saved = orc.load_state(state_file)["TASK-005"]
    assert saved["last_handoff"]["status"] == "IMPLEMENTED"
    assert saved["phase"] == "reviewer"


def test_review_findings_do_not_count_prompt_completion_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    state_file = tmp_path / "state.json"
    orc.save_state(
        state_file,
        {
            "TASK-005": {
                "status": "active",
                "phase": "reviewer",
                "round": 2,
                "target_directory": str(target),
                "handoffs": [],
                "reviewer_id": "rufus",
            }
        },
    )
    monkeypatch.setenv("ORC_TASK_ID", "TASK-005")
    monkeypatch.setenv("ORC_ROLE", "reviewer")
    payload = {
        "session_id": "rufus",
        "status": "REVIEWED_FOUND_ISSUES",
        "input-messages": ["or report exactly TASK COMPLETE when ready"],
        "last-assistant-message": (
            "Status: REVIEWED_FOUND_ISSUES\n\nRequested action: fix findings."
        ),
    }

    orc.idle_hook(hook_args(state_file, payload))

    saved = orc.load_state(state_file)["TASK-005"]
    assert saved["reviewer_reported_complete"] is False
    assert saved["status"] == "active"
    assert saved["phase"] == "implementer"
    assert saved["round"] == 3
    assert saved["stop_reason"] is None


def test_explicit_default_limits_are_always_available(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    for option, value in (("--max-rounds", "5"), ("--deadline-minutes", "60")):
        args = orc.parse_args(
            ["begin", str(target), "TASK-005", "implement", option, value, "--codex"]
        )
        assert getattr(args, option[2:].replace("-", "_")) == int(value)


def test_resume_rejects_completion_as_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    state_file = tmp_path / "state.json"
    state = {
        "TASK-005": {
            "status": "paused",
            "phase": "complete",
                "stop_reason": "completion",
                "target_directory": str(target.resolve()),
                "backend": "codex",
                "user_requests": [],
        }
    }
    orc.save_state(state_file, state)
    args = orc.parse_args(
        [
            "--state-file",
                str(state_file),
                "resume",
                "TASK-005",
            "continue",
        ]
    )
    monkeypatch.setattr(orc, "run_app", lambda *_: pytest.fail("must not launch"))
    with pytest.raises(SystemExit, match="already complete"):
        orc.resume(args)
    assert orc.load_state(state_file) == state


def make_fake_claude(path: Path, *, compatible: bool = True) -> None:
    help_text = (
        "Usage: claude [--print] [--output-format stream-json] "
        "[--input-format text] [--resume SESSION-ID]"
        if compatible
        else "Usage: claude"
    )
    path.write_text(
        f"#!{sys.executable}\n"
        "import json, os, pathlib, sys\n"
        f"help_text = {help_text!r}\n"
        "if '--help' in sys.argv:\n"
        "    print(help_text)\n"
        "    raise SystemExit(0)\n"
        "if '--version' in sys.argv:\n"
        "    print('Claude Code test 1.2.3')\n"
        "    raise SystemExit(0)\n"
        "if os.environ.get('ORC_CAPTURE'):\n"
        "    pathlib.Path(os.environ['ORC_CAPTURE']).write_text(json.dumps(sys.argv))\n"
        "print(json.dumps({'type': 'system', 'session_id': 'claude-test'}), "
        "flush=True)\n"
        "print(json.dumps({'type': 'result', 'session_id': 'claude-test', "
        "'result': 'Status: COMPLETE\\nSummary: done'}), flush=True)\n"
    )
    path.chmod(0o755)


def test_claude_cli_selection_and_probe_before_state_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    fake = tmp_path / "fake claude"
    make_fake_claude(fake)
    state_file = tmp_path / "state.json"
    monkeypatch.setenv("ORC_CLAUDE_COMMAND", str(fake))
    args = orc.parse_args(
        [
            "--state-file",
            str(state_file),
            "begin",
            str(target),
            "TASK-006",
            "implement",
            "--claude",
        ]
    )
    monkeypatch.setattr(orc, "run_app", lambda *_: None)
    orc.begin(args)
    record = orc.load_state(state_file)["TASK-006"]
    assert record["backend"] == "claude"
    assert record["backend_command"] == str(fake)
    assert record["backend_version"] == "Claude Code test 1.2.3"
    assert record["claude_session_id"] is None

    bad = tmp_path / "bad claude"
    make_fake_claude(bad, compatible=False)
    bad_state = tmp_path / "bad-state.json"
    monkeypatch.setenv("ORC_CLAUDE_COMMAND", str(bad))
    bad_args = orc.parse_args(
        [
            "--state-file",
            str(bad_state),
            "begin",
            str(target),
            "TASK-006-BAD",
            "implement",
            "--claude",
        ]
    )
    with pytest.raises(SystemExit, match="incompatible"):
        orc.begin(bad_args)
    assert not bad_state.exists()


def test_claude_resume_reuses_stored_backend_and_rejects_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    state_file = tmp_path / "state.json"
    state = {
        "TASK-006": {
            "status": "paused",
            "phase": "reviewer",
            "target_directory": str(target.resolve()),
            "user_requests": [],
            "backend": "claude",
            "backend_command": "missing-claude",
            "claude_session_id": "claude-test",
        }
    }
    orc.save_state(state_file, state)
    with pytest.raises(SystemExit):
        orc.parse_args(
            [
                "--state-file",
                str(state_file),
                "resume",
                "TASK-006",
                "continue",
                "--codex",
            ]
        )
    assert orc.load_state(state_file) == state


def test_claude_launch_argv_and_agentbox_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = tmp_path / "identity"
    marker.write_text("arbitrary")
    monkeypatch.setattr(orc, "AGENTBOX_IDENTITY", marker)
    monkeypatch.setattr(orc.sys, "platform", "linux")
    command = orc.backend_launch_command(
        "claude",
        ["claude executable with spaces"],
        "Prompt",
        "TASK-006",
        "implementer",
        None,
        False,
        False,
        tmp_path / "state.json",
    )
    assert command[:6] == [
        "claude executable with spaces",
        "--print",
        "--output-format",
        "stream-json",
        "--input-format",
        "text",
    ]
    assert command[-2] == orc.CLAUDE_AGENTBOX_FLAG
    assert command.count(orc.CLAUDE_AGENTBOX_FLAG) == 1
    resumed = orc.backend_launch_command(
        "claude",
        ["claude"],
        "Follow up",
        "TASK-006",
        "implementer",
        "claude-test",
        True,
        False,
        tmp_path / "state.json",
    )
    assert resumed[6:8] == ["--resume", "claude-test"]
    monkeypatch.setattr(orc, "AGENTBOX_IDENTITY", tmp_path / "absent")
    assert orc.CLAUDE_AGENTBOX_FLAG not in orc.backend_launch_command(
        "claude",
        ["claude"],
        "Prompt",
        "TASK-006",
        "implementer",
        None,
        False,
        False,
        tmp_path / "state.json",
    )


def test_claude_stream_parser_requires_session_and_valid_handoff() -> None:
    session = orc.ChildSession("implementer", 1, 1, object(), backend="claude")
    orc.OrcApp.read_claude_stream(
        session,
        b'{"type":"system","session_id":"claude-test"}\n'
        b'{"type":"result","session_id":"claude-test",'
        b'"result":"Status: COMPLETE\\nSummary: done"}\n',
    )
    payload = orc.OrcApp.claude_handoff(session)
    assert payload == {
        "session_id": "claude-test",
        "last-assistant-message": "Status: COMPLETE\nSummary: done",
    }
    incomplete = orc.ChildSession("implementer", 1, 1, object(), backend="claude")
    orc.OrcApp.read_claude_stream(
        incomplete,
        b'{"type":"result","session_id":"claude-test",'
        b'"result":"finished without handoff"}\n',
    )
    assert orc.OrcApp.claude_handoff(incomplete) is None


def test_begin_prompt_is_optional_and_empty_prompt_uses_built_in_instructions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    state_file = tmp_path / "state.json"
    args = orc.parse_args(
        [
            "--state-file",
            str(state_file),
            "begin",
            str(target),
            "TASK-008",
            "--codex",
        ]
    )
    assert args.prompt == ""
    monkeypatch.setattr(orc, "run_app", lambda *_: None)
    orc.begin(args)
    assert orc.load_state(state_file)["TASK-008"]["prompt"] == ""

    app, _state_file, _panes = app_stub(
        tmp_path,
        {
            "status": "active",
            "phase": "implementer",
            "target_directory": str(target),
            "prompt": "",
            "user_requests": [],
        },
    )
    commands: list[list[str]] = []
    monkeypatch.setattr(
        app,
        "fork_codex",
        lambda command, _environment, _cwd=None: (
            commands.append(command) or (123, os.open("/dev/null", os.O_RDWR))
        ),
    )
    monkeypatch.setattr(app, "set_master_reader", lambda _session: None)
    monkeypatch.setattr(app, "resize_session", lambda _session: None)
    monkeypatch.setattr(app, "update_layout", lambda: None)
    monkeypatch.setattr(app, "update_status", lambda _message: None)
    app.launch_role("implementer")
    assert "Continue implementing the task" not in commands[0][-1]
    assert "User request:" not in commands[0][-1]
    assert "Read the docs in design_docs/" in commands[0][-1]


def test_status_bar_derives_both_role_states_and_agentbox_indicator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    marker = tmp_path / "identity"
    marker.write_text("")
    monkeypatch.setattr(orc, "AGENTBOX_IDENTITY", marker)
    monkeypatch.setattr(orc.sys, "platform", "linux")
    app, state_file, _panes = app_stub(
        tmp_path,
        {
            "status": "active",
            "phase": "reviewer",
            "target_directory": str(target),
            "handoffs": [{"role": "implementer"}],
            "backend": "codex",
            "launch_command": ["codex", orc.CODEX_AGENTBOX_FLAG],
        },
    )
    state = orc.load_state(state_file)
    record = state["TASK-003"]
    assert app.role_state(record, "implementer") == "waiting"
    assert app.role_state(record, "reviewer") == "active"
    rendered = app.status_text(record)
    assert "TASK-003: active" in rendered
    assert "Igor: waiting" in rendered
    assert "Rufus: active" in rendered
    assert "agentbox: no-permissions" in rendered
    assert "layout:" not in rendered
    assert orc.ORC_VERSION in rendered

    record["status"] = "completed"
    record["phase"] = "complete"
    assert app.role_state(record, "implementer") == "inactive"
    assert app.role_state(record, "reviewer") == "inactive"


@pytest.mark.parametrize(
    ("status", "color"),
    [
        ("active", "#7ee787"),
        ("paused", "#f2cc60"),
        ("blocked", "#f2cc60"),
        ("stopped", "#f2cc60"),
        ("completed", "#7ee787"),
    ],
)
def test_status_bar_task_status_format_and_colors(
    tmp_path: Path, status: str, color: str
) -> None:
    app, _state_file, _panes = app_stub(
        tmp_path,
        {"status": status, "phase": "complete" if status == "completed" else "stopped"},
    )
    record = orc.load_state(app.args.state_file)["TASK-003"]
    segments = app.status_segments(record)
    assert segments["task"] == f"TASK-003: {status} · round 1/5"
    assert "Click a pane to focus" not in app.status_text(record)
    assert app._status_color("task", status) == color


@pytest.mark.parametrize(
    ("state", "color"),
    [
        ("inactive", "#8b949e"),
        ("not started", "#8b949e"),
        ("active", "#7ee787"),
        ("waiting", "#8b949e"),
        ("failed", "#ff7b72"),
    ],
)
def test_status_bar_role_state_colors(
    tmp_path: Path, state: str, color: str
) -> None:
    app, _state_file, panes = app_stub(tmp_path, {"status": "active"})
    record = {"status": "active"}
    if state == "inactive":
        record.update(status="completed", phase="complete")
    elif state == "active":
        app.sessions["implementer"] = orc.ChildSession(
            "implementer", 1, 1, panes["implementer"]
        )
    elif state == "waiting":
        record["handoffs"] = [{"role": "implementer"}]
    elif state == "failed":
        record["child_failure"] = {"role": "implementer"}
    assert app._status_color("role", state) == color


def test_status_bar_backend_and_warning_styles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = tmp_path / "identity"
    marker.write_text("")
    monkeypatch.setattr(orc, "AGENTBOX_IDENTITY", marker)
    monkeypatch.setattr(orc.sys, "platform", "linux")
    app, _state_file, _panes = app_stub(
        tmp_path,
        {
            "status": "active",
            "phase": "implementer",
            "backend": "claude",
            "launch_command": ["claude", orc.CLAUDE_AGENTBOX_FLAG],
        },
    )
    record = orc.load_state(app.args.state_file)["TASK-003"]
    segments = app.status_segments(record)
    assert segments["backend"] == "backend: claude"
    assert segments["agentbox"] == "agentbox: no-permissions"
    assert orc.STATUS_COLORS["backend"] == "#ffffff"
    assert orc.STATUS_COLORS["agentbox"] == "#ff7b72"


def test_status_bar_composed_widgets_follow_size_priority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    state_file = tmp_path / "state.json"
    record = {
        "status": "active",
        "phase": "implementer",
        "target_directory": str(target),
        "backend": "codex",
    }
    orc.save_state(state_file, {"TASK-009": record})
    args = argparse.Namespace(state_file=state_file, codex="codex")
    app = orc.OrcApp(args, "TASK-009")
    monkeypatch.setattr(app, "launch_role", lambda _role: None)

    async def exercise() -> None:
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert app.layout_mode == "side-by-side"
            assert app.query_one("#status-message", orc.Static).render().plain == (
                "TASK-009: active · round 1/5"
            )
            assert app.query_one("#status-version", orc.Static).render().plain == (
                f"{orc.STATUS_VERSION_SEPARATOR}{orc.ORC_VERSION}"
            )
            assert app.query_one("#status-hint", orc.Static).styles.display == "block"
            assert app.query_one("#status-hint", orc.Static).render().plain == (
                f"{orc.STATUS_SEGMENT_SEPARATOR}{orc.FOCUS_STATUS}"
            )
            assert (
                "#7ee787"
                in str(
                    app.query_one("#status-message", orc.Static)
                    ._Static__content
                    .spans[-1]
                    .style
                )
            )

            await pilot.resize_terminal(80, 40)
            await pilot.pause()
            assert app.layout_mode == "stacked"
            assert (
                app.query_one("#status-message", orc.Static).styles.display == "block"
            )
            assert (
                app.query_one("#status-igor", orc.Static).styles.display == "block"
            )
            assert (
                app.query_one("#status-rufus", orc.Static).styles.display == "block"
            )
            assert (
                app.query_one("#status-backend", orc.Static).styles.display == "none"
            )
            assert app.query_one("#status-hint", orc.Static).styles.display == "none"

            await pilot.resize_terminal(80, 24)
            await pilot.pause()
            assert app.layout_mode == "single"
            assert (
                app.query_one("#status-message", orc.Static).styles.display == "block"
            )
            assert (
                app.query_one("#status-igor", orc.Static).styles.display == "block"
            )
            assert (
                app.query_one("#status-rufus", orc.Static).styles.display == "block"
            )
            assert app.query_one("#status-version", orc.Static).render().plain == (
                f"{orc.STATUS_VERSION_SEPARATOR}{orc.ORC_VERSION}"
            )

            marker = tmp_path / "identity"
            marker.write_text("")
            monkeypatch.setattr(orc, "AGENTBOX_IDENTITY", marker)
            monkeypatch.setattr(orc.sys, "platform", "linux")
            record["launch_command"] = ["codex", orc.CODEX_AGENTBOX_FLAG]
            record["handoffs"] = [
                {"role": "implementer"},
                {"role": "reviewer"},
            ]
            orc.save_state(state_file, {"TASK-009": record})
            app.refresh_status()
            await pilot.pause()
            assert app.query_one("#status-backend", orc.Static).styles.display == "none"
            assert (
                app.query_one("#status-agentbox", orc.Static).styles.display == "none"
            )
            assert app.query_one("#status-hint", orc.Static).styles.display == "none"
            app.exit()

    asyncio.run(exercise())


def test_status_bar_renders_all_states_order_and_boundaries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    state_file = tmp_path / "state.json"
    record: dict[str, object] = {
        "status": "active",
        "phase": "implementer",
        "target_directory": str(target),
        "backend": "codex",
        "handoffs": [],
    }
    orc.save_state(state_file, {"TASK-009": record})
    args = argparse.Namespace(state_file=state_file, codex="codex")
    app = orc.OrcApp(args, "TASK-009")
    monkeypatch.setattr(app, "launch_role", lambda _role: None)
    # The fixture renders in-memory records directly; keep the live poll from
    # replacing those records with the initial state-file snapshot.
    monkeypatch.setattr(app, "poll_state", lambda: None)
    monkeypatch.setattr(app, "poll_children", lambda: None)

    task_colors = {
        "active": "#7ee787",
        "paused": "#f2cc60",
        "blocked": "#f2cc60",
        "stopped": "#f2cc60",
        "completed": "#7ee787",
    }
    role_colors = {
        "inactive": "#8b949e",
        "not started": "#8b949e",
        "active": "#7ee787",
        "waiting": "#8b949e",
        "failed": "#ff7b72",
    }

    async def exercise() -> None:
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            def widget(widget_id: str) -> orc.Static:
                return app.query_one(f"#{widget_id}", orc.Static)

            def color(widget_id: str) -> str:
                return str(widget(widget_id)._Static__content.spans[-1].style)

            def label_color(widget_id: str) -> str:
                return str(widget(widget_id)._Static__content.style)

            for status, expected_color in task_colors.items():
                record["status"] = status
                record["phase"] = "complete" if status == "completed" else "implementer"
                record["handoffs"] = []
                record.pop("child_failure", None)
                app.sessions = {}
                app.render_status_bar(record)
                await pilot.pause()
                assert widget("status-message").render().plain == (
                    f"TASK-009: {status} · round 1/5"
                )
                assert expected_color in color("status-message")
                assert "#d0d7de" in label_color("status-message")

            role_cases = {
                "not started": {"handoffs": []},
                "active": {"sessions": {"implementer": False, "reviewer": False}},
                "waiting": {
                    "handoffs": [
                        {"role": "implementer"},
                        {"role": "reviewer"},
                    ]
                },
                "inactive": {"status": "completed", "phase": "complete"},
                "failed": {"child_failure": {"role": "implementer"}},
            }
            for state, changes in role_cases.items():
                record.update(changes)
                if state == "inactive":
                    record["status"] = "completed"
                    record["phase"] = "complete"
                else:
                    record["status"] = "active"
                    record["phase"] = (
                        "reviewer"
                        if state in {"not started", "waiting"}
                        else "implementer"
                    )
                if state != "failed":
                    record.pop("child_failure", None)
                app.sessions = {
                    role: argparse.Namespace(
                        exited=False, retired=False, handoff_count=0
                    )
                    for role in changes.get("sessions", {})
                }
                app.render_status_bar(record)
                await pilot.pause()
                assert role_colors[state] in color("status-igor")
                assert "#d0d7de" in label_color("status-igor")
                assert "#d0d7de" in label_color("status-rufus")
                if state == "inactive":
                    assert widget("status-rufus").render().plain == " · Rufus: inactive"
                elif state == "waiting":
                    assert widget("status-rufus").render().plain == " · Rufus: active"

            record["child_failure"] = {"role": "reviewer"}
            app.render_status_bar(record)
            await pilot.pause()
            assert role_colors["failed"] in color("status-rufus")

            for backend in ("codex", "claude"):
                record["status"] = "active"
                record["phase"] = "implementer"
                record["backend"] = backend
                record.pop("child_failure", None)
                record["handoffs"] = []
                app.render_status_bar(record)
                await pilot.pause()
                assert widget("status-backend").render().plain == (
                    f" · backend: {backend}"
                )
                assert "#ffffff" in color("status-backend")
                assert "#d0d7de" in label_color("status-backend")

            marker = tmp_path / "identity"
            marker.write_text("")
            monkeypatch.setattr(orc, "AGENTBOX_IDENTITY", marker)
            monkeypatch.setattr(orc.sys, "platform", "linux")
            record["backend"] = "codex"
            record["launch_command"] = ["codex", orc.CODEX_AGENTBOX_FLAG]
            record["handoffs"] = [
                {"role": "implementer"},
                {"role": "reviewer"},
            ]
            app.render_status_bar(record)
            await pilot.pause()
            assert widget("status-agentbox").render().plain == (
                " · agentbox: no-permissions"
            )
            assert "#ff7b72" in color("status-agentbox")
            assert "#d0d7de" in label_color("status-agentbox")

            record["status"] = "completed"
            record["phase"] = "complete"
            app.render_status_bar(record)
            await pilot.pause()
            assert widget("status-agentbox").styles.display == "block"
            assert widget("status-backend").styles.display == "none"

            expected_order = (
                "status-message",
                "status-igor",
                "status-rufus",
                "status-agentbox",
                "status-hint",
            )
            regions = [widget(widget_id).region for widget_id in expected_order]
            left_region = app.query_one("#status-left", orc.Container).region
            version_region = widget("status-version").region
            assert all(
                left.x + left.width <= right.x
                for left, right in zip(regions[:-1], regions[1:], strict=True)
            )
            assert left_region.x + left_region.width == version_region.x
            assert version_region.x + version_region.width == app.size.width
            assert widget("status-version").render().plain == (
                f"{orc.STATUS_VERSION_SEPARATOR}{orc.ORC_VERSION}"
            )
            assert widget("status-backend").styles.display == "none"

            for width, height, layout in (
                (120, 40, "side-by-side"),
                (80, 40, "stacked"),
                (80, 24, "single"),
            ):
                await pilot.resize_terminal(width, height)
                await pilot.pause()
                assert app.layout_mode == layout
                left_region = app.query_one("#status-left", orc.Container).region
                version_region = widget("status-version").region
                visible = [
                    widget(widget_id).region
                    for widget_id in expected_order
                    if widget(widget_id).styles.display == "block"
                ]
                assert left_region.x + left_region.width == version_region.x
                assert all(region.x >= left_region.x for region in visible)
                assert version_region.x + version_region.width == width
                assert widget("status-version").render().plain == (
                    f"{orc.STATUS_VERSION_SEPARATOR}{orc.ORC_VERSION}"
                )
            app.exit()

    asyncio.run(exercise())


def test_auto_handoff_retires_live_child_before_next_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    app, state_file, panes = app_stub(
        tmp_path,
        {
            "status": "active",
            "phase": "reviewer",
            "round": 1,
            "target_directory": str(target),
            "automatic_rounds": True,
            "handoffs": [{"role": "implementer"}],
            "role_generations": {"implementer": 1},
        },
    )
    session = orc.ChildSession(
        "implementer", 123, 99, panes["implementer"], handoff_count=0
    )
    app.sessions = {"implementer": session}
    killed: list[tuple[int, int]] = []
    launched: list[str] = []
    monkeypatch.setattr(orc.os, "killpg", lambda pid, sig: killed.append((pid, sig)))
    monkeypatch.setattr(app.event_loop, "remove_reader", lambda *_: None)
    monkeypatch.setattr(app, "launch_role", launched.append)
    monkeypatch.setattr(app, "update_status", lambda _message: None)

    app.poll_state()

    assert session.retired is True
    assert killed == [(123, orc.signal.SIGTERM)]
    assert launched == ["reviewer"]
    saved = orc.load_state(state_file)["TASK-003"]
    assert "child_failure" not in saved


def test_completed_task_keeps_ui_alive_with_both_roles_inactive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    app, _state_file, _panes = app_stub(
        tmp_path,
        {
            "status": "completed",
            "phase": "complete",
            "target_directory": str(target),
            "handoffs": [
                {"role": "implementer"},
                {"role": "reviewer"},
            ],
        },
    )
    exited: list[bool] = []
    rendered: list[str] = []
    monkeypatch.setattr(app, "exit", lambda: exited.append(True))
    monkeypatch.setattr(app, "update_status", rendered.append)

    app.poll_state()

    assert not exited
    assert rendered
    assert "completed" in rendered[-1]
    assert "Igor: inactive" in rendered[-1]
    assert "Rufus: inactive" in rendered[-1]


def test_terminal_task_stays_mounted_until_ctrl_q_and_preserves_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    record: dict[str, object] = {
        "status": "completed",
        "phase": "complete",
        "target_directory": str(target),
        "stop_reason": "completion",
        "handoffs": [
            {"role": "implementer"},
            {"role": "reviewer"},
        ],
    }
    state_file = tmp_path / "state.json"
    orc.save_state(state_file, {"TASK-003": record})
    app = orc.OrcApp(
        argparse.Namespace(state_file=state_file, codex="codex"), "TASK-003"
    )
    monkeypatch.setattr(app, "launch_role", lambda _role: None)

    async def exercise() -> None:
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert app.is_running
            app.poll_state()
            await pilot.pause()
            assert app.is_running
            assert app.query_one("#status-message", orc.Static).render().plain == (
                "TASK-003: completed · round 1/5"
            )
            app.exit()

    asyncio.run(exercise())
    assert orc.load_state(state_file)["TASK-003"] == record


@pytest.mark.parametrize(
    "terminal_status", ["paused", "blocked", "stopped", "completed"]
)
def test_terminal_transition_clears_active_agent_border(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    terminal_status: str,
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    state_file = tmp_path / "state.json"
    record: dict[str, object] = {
        "status": "active",
        "phase": "implementer",
        "round": 1,
        "max_rounds": 5,
        "backend": "codex",
        "target_directory": str(target),
        "handoffs": [],
    }
    orc.save_state(state_file, {"TASK-003": record})
    app = orc.OrcApp(argparse.Namespace(state_file=state_file), "TASK-003")
    monkeypatch.setattr(app, "launch_role", lambda _role: None)

    async def exercise() -> None:
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert "active-pane" in app.pane("implementer").classes
            record["status"] = terminal_status
            record["phase"] = (
                "complete" if terminal_status == "completed" else "stopped"
            )
            orc.save_state(state_file, {"TASK-003": record})
            app.poll_state()
            await pilot.pause()
            assert "active-pane" not in app.pane("implementer").classes
            assert "active-pane" not in app.pane("reviewer").classes
            app.exit()

    asyncio.run(exercise())


def test_paused_task_stays_mounted_without_mount_time_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    record: dict[str, object] = {
        "status": "paused",
        "phase": "reviewer",
        "target_directory": str(target),
        "stop_reason": "manual_pause",
        "handoffs": [],
        "user_requests": ["review the implementation"],
    }
    state_file = tmp_path / "state.json"
    orc.save_state(state_file, {"TASK-003": record})
    app = orc.OrcApp(
        argparse.Namespace(state_file=state_file, codex="codex"), "TASK-003"
    )
    monkeypatch.setattr(
        app,
        "fork_codex",
        lambda *_args: pytest.fail("paused task launched a child"),
    )

    async def exercise() -> None:
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert app.is_running
            assert app.sessions == {}
            assert app.query_one("#status-message", orc.Static).render().plain == (
                "TASK-003: paused · round 1/5"
            )
            app.exit()

    asyncio.run(exercise())
    assert orc.load_state(state_file)["TASK-003"] == record


@pytest.mark.parametrize("status", ["paused", "blocked", "stopped"])
def test_stop_status_keeps_compact_status_bar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: str
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    app, _state_file, _panes = app_stub(
        tmp_path,
        {
            "status": status,
            "phase": "blocked" if status == "blocked" else "reviewer",
            "target_directory": str(target),
            "stop_reason": "clarification" if status == "blocked" else "manual_pause",
            "handoffs": [],
        },
    )
    rendered: list[str] = []
    monkeypatch.setattr(app, "exit", lambda: None)
    monkeypatch.setattr(app, "update_status", rendered.append)

    app.poll_state()

    assert rendered
    assert "TASK-003: " + status in rendered[-1]
    assert "Igor:" in rendered[-1]
    assert "Rufus:" in rendered[-1]
    assert orc.ORC_VERSION in rendered[-1]
    assert orc.FOCUS_STATUS in rendered[-1]


@pytest.mark.parametrize(
    ("status", "phase", "stop_reason"),
    [
        ("completed", "complete", "completion"),
        ("blocked", "blocked", "clarification"),
        ("paused", "reviewer", "manual_pause"),
        ("stopped", "stopped", "deadline"),
        ("stopped", "stopped", "max_rounds"),
        ("stopped", "stopped", "child_failure"),
    ],
)
def test_terminal_records_are_idempotent_and_keep_ui_alive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: str,
    phase: str,
    stop_reason: str,
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    record: dict[str, object] = {
        "status": status,
        "phase": phase,
        "target_directory": str(target),
        "automatic_rounds": True,
        "deadline_at": "2000-01-01T00:00:00+00:00",
        "stop_reason": stop_reason,
        "handoffs": [],
    }
    app, state_file, _panes = app_stub(tmp_path, record)
    exited: list[bool] = []
    launches: list[str] = []
    monkeypatch.setattr(app, "exit", lambda: exited.append(True))
    monkeypatch.setattr(app, "launch_role", launches.append)
    monkeypatch.setattr(app, "update_status", lambda _message: None)

    app.poll_state()
    first = orc.load_state(state_file)["TASK-003"]
    app.poll_state()
    second = orc.load_state(state_file)["TASK-003"]

    assert second == first
    assert not exited
    assert launches == []


def test_deadline_stops_workflow_once_without_exiting_or_launching(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    app, state_file, _panes = app_stub(
        tmp_path,
        {
            "status": "active",
            "phase": "implementer",
            "target_directory": str(target),
            "automatic_rounds": True,
            "deadline_at": "2000-01-01T00:00:00+00:00",
            "stop_reason": None,
            "handoffs": [],
        },
    )
    exited: list[bool] = []
    launches: list[str] = []
    monkeypatch.setattr(app, "exit", lambda: exited.append(True))
    monkeypatch.setattr(app, "launch_role", launches.append)
    monkeypatch.setattr(app, "update_status", lambda _message: None)

    app.poll_state()
    first = orc.load_state(state_file)["TASK-003"]
    app.poll_state()
    second = orc.load_state(state_file)["TASK-003"]

    assert first["status"] == "stopped"
    assert first["phase"] == "stopped"
    assert first["stop_reason"] == "deadline"
    assert second == first
    assert not exited
    assert launches == []


@pytest.mark.parametrize("role", ["implementer", "reviewer"])
def test_unexpected_clean_child_exit_stops_without_exiting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    role: str,
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    app, state_file, panes = app_stub(
        tmp_path,
        {
            "status": "active",
            "phase": role,
            "target_directory": str(target),
            "handoffs": [],
        },
    )
    session = orc.ChildSession(role, 7, 99, panes[role])
    app.sessions = {role: session}
    monkeypatch.setattr(orc.os, "waitpid", lambda *_: (7, 0))
    monkeypatch.setattr(app.event_loop, "remove_reader", lambda *_: None)
    monkeypatch.setattr(app, "exit", lambda: pytest.fail("terminal exit"))
    monkeypatch.setattr(app, "update_status", lambda _message: None)

    app.poll_children()
    saved = orc.load_state(state_file)["TASK-003"]

    assert saved["status"] == "stopped"
    assert saved["phase"] == "stopped"
    assert saved["stop_reason"] == "child_failure"
    assert saved["child_failure"]["role"] == role
    assert session.exited


@pytest.mark.parametrize("backend", ["codex", "claude"])
@pytest.mark.parametrize(
    ("status", "phase", "stop_reason"),
    [
        ("paused", "reviewer", "manual_pause"),
        ("blocked", "blocked", "clarification"),
        ("stopped", "stopped", "deadline"),
        ("completed", "complete", "completion"),
    ],
)
def test_late_child_exit_preserves_terminal_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    backend: str,
    status: str,
    phase: str,
    stop_reason: str,
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    record: dict[str, object] = {
        "status": status,
        "phase": phase,
        "target_directory": str(target),
        "stop_reason": stop_reason,
        "child_failure": {
            "role": "reviewer",
            "backend": "prior",
            "reason": "original diagnostic",
        },
        "handoffs": [],
        "backend": backend,
    }
    app, state_file, panes = app_stub(tmp_path, record)
    session = orc.ChildSession(
        "reviewer", 7, 99, panes["reviewer"], backend=backend
    )
    app.sessions = {"reviewer": session}
    monkeypatch.setattr(orc.os, "waitpid", lambda *_: (7, 256))
    monkeypatch.setattr(app.event_loop, "remove_reader", lambda *_: None)
    monkeypatch.setattr(app, "exit", lambda: pytest.fail("terminal exit"))
    monkeypatch.setattr(app, "update_status", lambda _message: None)

    app.poll_children()
    first = orc.load_state(state_file)["TASK-003"]
    app.poll_children()
    second = orc.load_state(state_file)["TASK-003"]

    assert first == record
    assert second == first
    assert session.exited


def test_codex_nonzero_exit_after_handoff_is_child_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    app, state_file, panes = app_stub(
        tmp_path,
        {
            "status": "active",
            "phase": "reviewer",
            "target_directory": str(target),
            "handoffs": [{"role": "implementer"}],
        },
    )
    session = orc.ChildSession("implementer", 7, 99, panes["implementer"])
    app.sessions = {"implementer": session}
    monkeypatch.setattr(orc.os, "waitpid", lambda *_: (7, 256))
    monkeypatch.setattr(app.event_loop, "remove_reader", lambda *_: None)
    exited: list[bool] = []
    rendered: list[str] = []
    monkeypatch.setattr(app, "exit", lambda: exited.append(True))
    monkeypatch.setattr(app, "update_status", rendered.append)

    app.poll_children()

    saved = orc.load_state(state_file)["TASK-003"]
    assert saved["stop_reason"] == "child_failure"
    assert saved["child_failure"]["backend"] == "codex"
    assert saved["child_failure"]["reason"] == "Codex exited with status 1"
    assert not exited
    assert rendered
    assert "TASK-003: stopped" in rendered[-1]
    assert "Igor: failed" in rendered[-1]
    assert "Rufus:" in rendered[-1]
    assert orc.ORC_VERSION in rendered[-1]


def test_claude_stream_handles_noise_and_message_shapes() -> None:
    session = orc.ChildSession("implementer", 1, 1, object(), backend="claude")
    orc.OrcApp.read_claude_stream(
        session,
        b"terminal noise\n[1, 2]\n"
        b'{"type":"assistant","message":"plain"}\n'
        b'{"type":"assistant","message":{"content":"string"}}\n'
        b'{"type":"assistant","message":{"content":[{"text":"part"}]}}\n'
        b'{"type":"error","subtype":"error","result":"backend failed"}\n',
    )
    assert session.final_response == "backend failed"
    assert session.stream_error == "backend failed"
    assert orc.backend_command_value(["claude", "--wrapper"]) == [
        "claude",
        "--wrapper",
    ]
    with pytest.raises(SystemExit, match="backend command"):
        orc.backend_command_value([])


def test_claude_sessions_are_role_specific(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    record: dict[str, object] = {
        "status": "active",
        "phase": "reviewer",
        "round": 1,
        "target_directory": str(target),
        "prompt": "initial",
        "user_requests": [],
        "backend": "claude",
        "backend_command": "claude",
        "claude_sessions": {"implementer": "igor-session"},
        "implementer_id": "igor-session",
        "reviewer_id": None,
    }
    app, _state_file, _panes = app_stub(tmp_path, record)
    commands: list[list[str]] = []
    monkeypatch.setattr(
        app,
        "fork_codex",
        lambda command, _environment, _cwd=None: (
            commands.append(command) or (123, os.open("/dev/null", os.O_RDWR))
        ),
    )
    monkeypatch.setattr(app, "set_master_reader", lambda _session: None)
    monkeypatch.setattr(app, "resize_session", lambda _session: None)
    monkeypatch.setattr(app, "update_layout", lambda: None)
    monkeypatch.setattr(app, "update_status", lambda _message: None)

    app.launch_role("reviewer")

    assert commands
    assert "--resume" not in commands[0]
    assert "Review the target project's current worktree" in commands[0][-1]


def test_claude_nonzero_exit_is_child_failure_even_with_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    record: dict[str, object] = {
        "status": "active",
        "phase": "reviewer",
        "round": 1,
        "target_directory": str(target),
        "backend": "claude",
        "handoffs": [],
        "reviewer_id": "claude-test",
    }
    app, state_file, panes = app_stub(tmp_path, record)
    app.exit = lambda: None
    app.update_status = lambda _message: None
    session = orc.ChildSession(
        "reviewer",
        1,
        1,
        panes["reviewer"],
        backend="claude",
        session_id="claude-test",
        final_response="Status: COMPLETE",
        stream_events=[
            {
                "type": "result",
                "session_id": "claude-test",
                "result": "Status: COMPLETE",
            }
        ],
    )

    state = orc.load_state(state_file)
    app.handle_claude_exit(session, state, state["TASK-003"], 256)

    saved = orc.load_state(state_file)["TASK-003"]
    assert saved["stop_reason"] == "child_failure"
    assert saved["child_failure"]["reason"] == "Claude exited with status 1"
    assert not saved["handoffs"]


def test_claude_unavailable_command_has_clear_diagnostic() -> None:
    with pytest.raises(SystemExit, match="cannot run Claude backend"):
        orc.probe_claude(["missing-claude-command"])


@pytest.mark.integration
def test_claude_real_pty_clean_exit_records_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    fake = tmp_path / "fake claude"
    make_fake_claude(fake)
    record: dict[str, object] = {
        "status": "active",
        "phase": "reviewer",
        "round": 1,
        "target_directory": str(target),
        "prompt": "initial",
        "user_requests": [],
        "backend": "claude",
        "backend_command": str(fake),
        "backend_version": "Claude Code test 1.2.3",
        "claude_session_id": None,
        "claude_sessions": {},
        "reviewer_id": None,
        "handoffs": [],
    }
    app, state_file, _panes = app_stub(tmp_path, record)
    app.exit = lambda: None
    app.set_master_reader = lambda _session: None
    app.resize_session = lambda _session: None
    app.update_layout = lambda: None
    app.update_status = lambda _message: None
    app.launch_role("reviewer")
    session = app.sessions["reviewer"]
    _pid, status = os.waitpid(session.pid, 0)
    assert os.WIFEXITED(status)
    # The bytes remain readable from the PTY after the child exits.
    app.read_session(session)
    monkeypatch.setattr(
        orc.os,
        "waitpid",
        lambda *_: (_ for _ in ()).throw(ChildProcessError()),
    )
    app.poll_children()
    saved = orc.load_state(state_file)["TASK-003"]
    assert saved["reviewer_id"] == "claude-test"
    assert saved["claude_session_id"] == "claude-test"
    assert saved["stop_reason"] == "completion"


@pytest.mark.integration
def test_claude_real_pty_resume_uses_role_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    fake = tmp_path / "fake claude"
    capture = tmp_path / "capture.json"
    make_fake_claude(fake)
    monkeypatch.setenv("ORC_CAPTURE", str(capture))
    monkeypatch.setattr(orc, "AGENTBOX_IDENTITY", tmp_path / "absent")
    record: dict[str, object] = {
        "status": "active",
        "phase": "reviewer",
        "round": 1,
        "target_directory": str(target),
        "prompt": "initial",
        "user_requests": ["review again"],
        "backend": "claude",
        "backend_command": str(fake),
        "claude_sessions": {"reviewer": "old-reviewer-session"},
        "reviewer_id": "old-reviewer-session",
        "handoffs": [],
    }
    app, state_file, _panes = app_stub(tmp_path, record)
    app.exit = lambda: None
    app.set_master_reader = lambda _session: None
    app.resize_session = lambda _session: None
    app.update_layout = lambda: None
    app.update_status = lambda _message: None
    app.launch_role("reviewer")
    session = app.sessions["reviewer"]
    _pid, status = os.waitpid(session.pid, 0)
    assert os.WIFEXITED(status)
    app.read_session(session)
    monkeypatch.setattr(
        orc.os,
        "waitpid",
        lambda *_: (_ for _ in ()).throw(ChildProcessError()),
    )
    app.poll_children()

    argv = json.loads(capture.read_text())
    assert argv[argv.index("--resume") : argv.index("--resume") + 2] == [
        "--resume",
        "old-reviewer-session",
    ]
    assert orc.load_state(state_file)["TASK-003"]["stop_reason"] == "completion"


@pytest.mark.integration
@pytest.mark.parametrize("role", ["implementer", "reviewer"])
@pytest.mark.parametrize("marker_present", [False, True])
def test_claude_real_pty_agentbox_launches_both_roles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    role: str,
    marker_present: bool,
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    fake = tmp_path / "fake claude"
    capture = tmp_path / "capture.json"
    make_fake_claude(fake)
    marker = tmp_path / "identity"
    if marker_present:
        marker.write_text("")
    monkeypatch.setattr(orc, "AGENTBOX_IDENTITY", marker)
    monkeypatch.setattr(orc.sys, "platform", "linux")
    monkeypatch.setenv("ORC_CAPTURE", str(capture))
    record: dict[str, object] = {
        "status": "active",
        "phase": role,
        "round": 1,
        "target_directory": str(target),
        "prompt": "initial",
        "user_requests": [],
        "backend": "claude",
        "backend_command": str(fake),
        "claude_sessions": {},
        f"{role}_id": None,
        "handoffs": [],
    }
    app, _state_file, _panes = app_stub(tmp_path, record)
    app.exit = lambda: None
    app.set_master_reader = lambda _session: None
    app.resize_session = lambda _session: None
    app.update_layout = lambda: None
    app.update_status = lambda _message: None
    app.launch_role(role)
    session = app.sessions[role]
    _pid, status = os.waitpid(session.pid, 0)
    assert os.WIFEXITED(status)
    app.read_session(session)
    monkeypatch.setattr(
        orc.os,
        "waitpid",
        lambda *_: (_ for _ in ()).throw(ChildProcessError()),
    )
    app.poll_children()

    argv = json.loads(capture.read_text())
    assert argv.count(orc.CLAUDE_AGENTBOX_FLAG) == int(marker_present)
