#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pyte>=0.8.2",
#   "rich>=13.0",
#   "textual>=1.0.0",
# ]
# ///
"""Orchestrate interactive Igor and Rufus Codex sessions in one terminal."""

from __future__ import annotations

import argparse
import asyncio
import errno
import fcntl
import json
import os
import signal
import struct
import subprocess
import sys
import termios
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyte
from rich.style import Style
from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Container
from textual.events import Click, Paste
from textual.geometry import Size
from textual.screen import Screen
from textual.widgets import Static

IMPLEMENTER_PROMPT = """
Read the docs in design_docs/ and docs/roles.md. You are Igor the implementer.
Following all of the rules for Igor is MANDATORY. Your work will primarily
come from what is described in design_docs/implementation_plan.md. If the
current commit has been pushed to origin/main start implementing the next NEW
task.
""".strip()

REVIEWER_PROMPT = """
Read the docs in design_docs/ and docs/roles.md. You are Rufus the reviewer.
Following all of the rules for Rufus is MANDATORY. You will review what Igor
implements from design_docs/implementation_plan.md. Wait to be told there is
a commit to review.
""".strip()

IMPLEMENTER_ROUND_PROMPT = """
Continue implementing the task. Inspect the current worktree and the latest
reviewer event, address every valid finding, and report your changes and
verification. When finished, become idle so Orc can start the next review.
""".strip()

HANDOFF_PROMPT = """
End your turn with a concise handoff containing: status, summary, files
changed, verification, blockers, and requested action. Orc will add the
authoritative UTC and local timestamps, task, role, round, thread, and commit
hash.
""".strip()

ORC_VERSION = "orc v0.0.1"
FOCUS_STATUS = "Click a pane to focus · Tab switches panes · Ctrl-Q exits"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Orchestrate Igor and Rufus Codex sessions. "
            "Usage: begin DIRECTORY TASK-ID PROMPT or "
            "resume DIRECTORY TASK-ID PROMPT."
        )
    )
    parser.add_argument(
        "--state-file",
        type=Path,
        default=Path.home() / ".orc" / "codex-state.json",
        help="Path for Orc state (default: %(default)s).",
    )
    parser.add_argument(
        "--codex",
        default=os.environ.get("CODEX_COMMAND", "codex"),
        help="Codex executable to invoke (default: %(default)s).",
    )

    commands = parser.add_subparsers(dest="command", required=True)

    begin = commands.add_parser("begin", help="Begin a task in DIRECTORY.")
    begin.add_argument(
        "directory",
        metavar="DIRECTORY",
        type=Path,
        help="Existing target project directory.",
    )
    begin.add_argument("task_id", help="Task identifier, such as TASK-001.")
    begin.add_argument("prompt", help="Initial request for Igor.")

    resume = commands.add_parser(
        "resume", help="Resume a task in its stored DIRECTORY."
    )
    resume.add_argument(
        "directory",
        metavar="DIRECTORY",
        type=Path,
        help="Existing target project directory matching the task state.",
    )
    resume.add_argument("task_id", help="Task identifier, such as TASK-001.")
    resume.add_argument(
        "prompt",
        help="Follow-up or new request for Igor in this task context.",
    )

    hook = commands.add_parser("idle-hook", help=argparse.SUPPRESS)
    hook.add_argument("payload", nargs="?")

    args = parser.parse_args(argv)
    # The child PTY changes its working directory to the target project.  An
    # absolute state path keeps the idle hook attached to Orc's state file
    # when the caller supplied a relative --state-file.
    args.state_file = args.state_file.expanduser().resolve()
    return args


def normalize_target_directory(value: Path) -> Path:
    """Return an absolute target directory, or a useful CLI error."""

    candidate = value.expanduser()
    try:
        normalized = candidate.resolve(strict=True)
    except FileNotFoundError as error:
        raise SystemExit(f"target directory does not exist: {value}") from error
    except (OSError, RuntimeError) as error:
        raise SystemExit(f"cannot access target directory {value}: {error}") from error
    if not normalized.is_dir():
        raise SystemExit(f"target directory is not a directory: {value}")
    return normalized


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"cannot read Orc state {path}: {error}") from error
    if not isinstance(value, dict):
        raise SystemExit(f"Orc state {path} must contain an object")
    return value


def save_state(path: Path, state: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    except OSError as error:
        raise SystemExit(f"cannot write Orc state {path}: {error}") from error


def session_name(task_id: str, role: str) -> str:
    return f"{task_id}-{role}"


def reviewer_prompt(record: dict[str, Any]) -> str:
    requests = [record.get("prompt")]
    requests.extend(record.get("user_requests", []))
    requests = [request for request in requests if isinstance(request, str)]
    request_text = "\n".join(f"- {request}" for request in requests)
    target = record.get("target_directory", "unknown")
    return (
        f"{REVIEWER_PROMPT}\n\n"
        f"Target project directory: {target}\n"
        "Review the target project's current worktree and Git repository. "
        "Do not review or modify Orc's repository.\n"
        "Igor has completed the implementation turn. Review the current "
        "worktree now. Do not implement fixes. Report findings and evidence, "
        "or report exactly TASK COMPLETE when ready.\n\n"
        f"User requests in this context:\n{request_text}"
    )


def session_id_from_payload(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in (
            "session_id",
            "session-id",
            "sessionId",
            "thread_id",
            "thread-id",
            "threadId",
            "id",
        ):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate:
                return candidate
        for nested in value.values():
            session_id = session_id_from_payload(nested)
            if session_id:
                return session_id
    elif isinstance(value, list):
        for nested in value:
            session_id = session_id_from_payload(nested)
            if session_id:
                return session_id
    return None


def assistant_message_from_payload(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ("last-assistant-message", "last_agent_message"):
            message = value.get(key)
            if isinstance(message, str) and message:
                return message
        for nested in value.values():
            message = assistant_message_from_payload(nested)
            if message:
                return message
    elif isinstance(value, list):
        for nested in value:
            message = assistant_message_from_payload(nested)
            if message:
                return message
    return None


def current_commit(cwd: str | Path | None) -> str:
    if cwd is None:
        return "unknown"
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=cwd,
            capture_output=True,
            check=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    commit = result.stdout.strip()
    return commit or "unknown"


def notify_config(state_file: Path) -> str:
    hook = [
        "uv",
        "run",
        "--script",
        str(Path(__file__).resolve()),
        "--state-file",
        str(state_file.expanduser().resolve()),
        "idle-hook",
    ]
    return json.dumps(hook, separators=(",", ":"))


def set_pty_size(fd: int, width: int, height: int) -> None:
    width = max(width, 2)
    height = max(height, 2)
    size = struct.pack("HHHH", height, width, 0, 0)
    try:
        fcntl.ioctl(fd, termios.TIOCSWINSZ, size)
    except (OSError, ValueError):
        pass


class SessionPane(Static):
    """A Textual widget backed by one emulated Codex terminal."""

    def __init__(self, role: str) -> None:
        self.role = role
        self.terminal_screen = pyte.Screen(80, 24)
        self.stream = pyte.Stream(self.terminal_screen)
        self.has_output = False
        self.has_visible_content = False
        self.message: str | None = f"{role.title()} not yet started."
        self.render_timer: Any = None
        super().__init__(
            self.message,
            id=role,
            classes="pane",
            markup=False,
        )

    def feed(self, data: bytes) -> None:
        self.stream.feed(data.decode("utf-8", errors="replace"))
        has_visible_content = any(line.strip() for line in self.terminal_screen.display)
        if has_visible_content:
            self.has_output = True
            self.has_visible_content = True
            self.message = None
            if self.is_attached:
                self.schedule_render()

    def resize_terminal(self, width: int, height: int) -> None:
        width = max(width, 2)
        height = max(height, 2)
        self.terminal_screen.resize(height, width)
        if self.has_visible_content and self.message is None:
            self.update(self.render_screen())

    def show_message(self, message: str) -> None:
        if self.render_timer is not None:
            self.render_timer.stop()
            self.render_timer = None
        self.message = message
        self.update(message)

    def schedule_render(self) -> None:
        if self.render_timer is None:
            self.render_timer = self.set_timer(1 / 30, self.flush_render)

    def flush_render(self) -> None:
        self.render_timer = None
        if self.has_visible_content and self.message is None:
            self.update(self.render_screen())

    @staticmethod
    def _rich_color(value: str) -> str | None:
        if value in {"", "default"}:
            return None
        if len(value) == 6 and all(digit in "0123456789abcdef" for digit in value):
            return f"#{value}"
        return value

    def render_screen(self) -> Text:
        rendered = Text()
        default_char = self.terminal_screen.default_char
        for row_index in range(self.terminal_screen.lines):
            row = self.terminal_screen.buffer[row_index]
            run_chars: list[str] = []
            run_style: (
                tuple[str | None, str | None, bool, bool, bool, bool, bool, bool] | None
            ) = None

            def flush_run() -> None:
                nonlocal run_chars, run_style
                if run_chars and run_style is not None:
                    rendered.append(
                        "".join(run_chars),
                        style=Style(
                            color=run_style[0],
                            bgcolor=run_style[1],
                            bold=run_style[2],
                            italic=run_style[3],
                            underline=run_style[4],
                            blink=run_style[5],
                            reverse=run_style[6],
                            strike=run_style[7],
                        ),
                    )
                run_chars = []
                run_style = None

            for column_index in range(self.terminal_screen.columns):
                char = row.get(column_index, default_char)
                style = (
                    self._rich_color(char.fg),
                    self._rich_color(char.bg),
                    char.bold,
                    char.italics,
                    char.underscore,
                    char.blink,
                    char.reverse,
                    char.strikethrough,
                )
                if style != run_style:
                    flush_run()
                    run_style = style
                run_chars.append(char.data)
            flush_run()
            if row_index < self.terminal_screen.lines - 1:
                rendered.append("\n")
        return rendered


class OrcScreen(Screen[None]):
    """Default screen that observes Textual's consumed resize event."""

    def _screen_resized(self, size: Size) -> None:
        super()._screen_resized(size)
        resize_handler = getattr(self.app, "on_terminal_resize", None)
        composed = getattr(self.app, "_compose_screen", None) is not None
        if resize_handler is not None and self.is_attached and composed:
            resize_handler(size)


@dataclass
class ChildSession:
    role: str
    pid: int
    master_fd: int
    pane: SessionPane
    exited: bool = False


class OrcApp(App[None]):
    """Own the terminal and multiplex the two interactive Codex PTYs."""

    CSS = """
    Screen {
        background: $surface;
    }

    #panes {
        width: 1fr;
        height: 1fr;
        layout: horizontal;
    }

    .pane {
        width: 1fr;
        height: 1fr;
        border: solid #555555;
        overflow: hidden;
    }

    .pane.active-pane {
        border: solid $primary;
    }

    #status {
        height: 1;
        background: $boost;
        color: $text;
        layout: horizontal;
    }

    #status-message {
        width: 1fr;
        padding: 0 1;
    }

    #version {
        width: auto;
        padding: 0 1;
    }
    """

    def __init__(self, args: argparse.Namespace, task_id: str) -> None:
        super().__init__()
        self.args = args
        self.task_id = task_id
        self.sessions: dict[str, ChildSession] = {}
        self.started_roles: set[str] = set()
        self.active_role = "implementer"
        self.layout_mode = ""
        self.last_status = "starting"
        self.event_loop: asyncio.AbstractEventLoop | None = None

    def get_default_screen(self) -> Screen:
        return OrcScreen(id="_default")

    def compose(self) -> ComposeResult:
        yield Container(
            SessionPane("implementer"),
            SessionPane("reviewer"),
            id="panes",
        )
        yield Container(
            Static(
                f"{self.task_id} · Starting Orc…",
                id="status-message",
                markup=False,
            ),
            Static(ORC_VERSION, id="version", markup=False),
            id="status",
        )

    def on_mount(self) -> None:
        if os.name != "posix":
            self.fatal_error("Orc's interactive PTY UI currently requires POSIX.")
            return
        self.event_loop = asyncio.get_running_loop()
        self.set_interval(0.1, self.poll_state)
        self.set_interval(0.1, self.poll_children)
        self.update_layout()
        self.call_after_refresh(self.launch_role, "implementer")

    def fatal_error(self, message: str) -> None:
        self.last_status = message
        self.exit()

    def pane(self, role: str) -> SessionPane:
        return self.query_one(f"#{role}", SessionPane)

    def launch_role(self, role: str) -> None:
        if role in self.started_roles:
            return

        state = load_state(self.args.state_file)
        record = state.get(self.task_id)
        if not isinstance(record, dict):
            self.fatal_error(f"no state for task {self.task_id}")
            return

        target_value = record.get("target_directory")
        if not isinstance(target_value, str) or not target_value:
            self.fatal_error(
                f"task {self.task_id} has no target directory in Orc state"
            )
            return
        target_directory = Path(target_value)

        if role == "implementer":
            prompt = (
                IMPLEMENTER_PROMPT
                if not record.get("user_requests")
                else IMPLEMENTER_ROUND_PROMPT
            )
            prompt += (
                f"\n\nTarget project directory: {target_directory}\n"
                "Work in the target project; Orc's repository contains only "
                "the orchestrator state and UI."
            )
            prompt += "\n\n" + HANDOFF_PROMPT
            if record.get("user_requests"):
                prompt += "\n\nUser request for this context:\n"
                prompt += str(record["user_requests"][-1])
            else:
                prompt += "\n\nUser request:\n" + str(record["prompt"])
        else:
            prompt = reviewer_prompt(record) + "\n\n" + HANDOFF_PROMPT

        command = [self.args.codex]
        # General Orc testing can keep the agent session in place by setting
        # ORC_DISABLE_IDLE_HOOK=1 for this launch.
        if os.environ.get("ORC_DISABLE_IDLE_HOOK") != "1":
            command.extend(
                [
                    "-c",
                    f"notify={notify_config(self.args.state_file)}",
                ]
            )
        thread_id = record.get(f"{role}_id")
        if isinstance(thread_id, str) and thread_id:
            requests = record.get("user_requests", [])
            if not isinstance(requests, list) or not requests:
                self.fatal_error(
                    f"cannot resume {role}: no user request recorded for task "
                    f"{self.task_id}"
                )
                return
            command.extend(["resume", thread_id, prompt])
        else:
            full_prompt = (
                f"{prompt}\n\nTask ID: {self.task_id}\n"
                f"Session name: {session_name(self.task_id, role)}"
            )
            command.append(full_prompt)

        environment = os.environ.copy()
        # The child is connected to Orc's ANSI-capable terminal emulator, not
        # directly to the caller's stdout.  Do not let a wrapper/container
        # level NO_COLOR setting disable Codex's screen colors in the pane.
        environment.pop("NO_COLOR", None)
        if not environment.get("TERM") or environment["TERM"] == "dumb":
            environment["TERM"] = "xterm-256color"
        environment["ORC_TASK_ID"] = self.task_id
        environment["ORC_ROLE"] = role
        environment["ORC_TARGET_DIRECTORY"] = str(target_directory)
        try:
            pid, master_fd = self.fork_codex(command, environment, target_directory)
        except OSError as error:
            self.fatal_error(f"could not launch {role}: {error}")
            return

        os.set_blocking(master_fd, False)
        pane = self.pane(role)
        pane.show_message(f"Starting {role.title()}…")
        session = ChildSession(role, pid, master_fd, pane)
        self.sessions[role] = session
        self.started_roles.add(role)
        self.active_role = role
        self.update_layout()
        self.set_master_reader(session)
        self.resize_session(session)
        self.schedule_resize()
        self.update_status(self.active_status())

    @staticmethod
    def fork_codex(
        command: list[str],
        environment: dict[str, str],
        cwd: Path | str | None = None,
    ) -> tuple[int, int]:
        pid, master_fd = os.forkpty()
        if pid == 0:
            try:
                if cwd is not None:
                    os.chdir(cwd)
                os.execvpe(command[0], command, environment)
            except OSError as error:
                os.write(2, f"orc: could not exec {command[0]}: {error}\n".encode())
                os._exit(127)
        return pid, master_fd

    def set_master_reader(self, session: ChildSession) -> None:
        if self.event_loop is None:
            raise RuntimeError("Orc event loop is not running")
        self.event_loop.add_reader(session.master_fd, self.read_session, session)

    def read_session(self, session: ChildSession) -> None:
        try:
            data = os.read(session.master_fd, 65536)
        except BlockingIOError:
            return
        except OSError as error:
            if error.errno not in (errno.EIO, errno.EBADF):
                self.update_status(f"{session.role.title()} PTY error: {error}")
            return
        if data:
            session.pane.feed(data)

    def write_active(self, data: bytes) -> None:
        session = self.sessions.get(self.active_role)
        if session is None or session.exited:
            return
        try:
            os.write(session.master_fd, data)
        except OSError as error:
            if error.errno not in (errno.EPIPE, errno.EBADF):
                self.update_status(f"could not write to {session.role}: {error}")

    def resize_session(self, session: ChildSession) -> None:
        width, height = self.pane_terminal_size(session.pane)
        set_pty_size(session.master_fd, width, height)
        session.pane.resize_terminal(width, height)

    @staticmethod
    def pane_terminal_size(pane: SessionPane) -> tuple[int, int]:
        """Return the rendered content size available to a child PTY."""

        content_size = getattr(pane, "content_size", None)
        if content_size is not None:
            width = getattr(content_size, "width", 0)
            height = getattr(content_size, "height", 0)
            if width or height:
                return max(width, 2), max(height, 2)

        # A pane may be measured before Textual has laid it out (startup) or
        # while it is hidden in single-pane mode. Keep a safe fallback for
        # those transient states without using the outer terminal dimensions.
        size = getattr(pane, "size", None)
        if size is None:
            return 2, 2
        gutter = getattr(getattr(pane, "styles", None), "gutter", None)
        if gutter is None:
            horizontal = vertical = 2
        else:
            horizontal = gutter.left + gutter.right
            vertical = gutter.top + gutter.bottom
        return max(size.width - horizontal, 2), max(size.height - vertical, 2)

    def resize_sessions(self) -> None:
        for session in getattr(self, "sessions", {}).values():
            if not session.exited:
                self.resize_session(session)

    def schedule_resize(self) -> None:
        """Repeat a resize after pending Textual layout work is applied."""

        if getattr(self, "_running", False):
            self.call_after_refresh(self.resize_sessions)

    def on_terminal_resize(self, _size: Size) -> None:
        self.update_layout()
        self.resize_sessions()
        self.schedule_resize()

    def on_resize(self, _event: Any) -> None:
        # Keep this handler for direct Resize messages and test drivers. The
        # mounted screen receives real terminal resizes first because Textual
        # consumes that event before it can bubble to the App.
        self.on_terminal_resize(_event)

    def active_status(self) -> str:
        layout = f" · layout: {self.layout_mode}" if self.layout_mode else ""
        return f"{self.active_role.title()} active{layout} · {FOCUS_STATUS}"

    def update_layout(self) -> None:
        if not self.is_running:
            return
        width = self.size.width
        height = self.size.height - 1
        panes = self.query_one("#panes", Container)

        if width >= 120 and width >= height * 1.35:
            mode = "side-by-side"
            panes.styles.layout = "horizontal"
        elif height >= 32:
            mode = "stacked"
            panes.styles.layout = "vertical"
        else:
            mode = "single"
            panes.styles.layout = "vertical"

        for role in ("implementer", "reviewer"):
            pane = self.pane(role)
            pane.styles.width = "1fr"
            pane.styles.height = "1fr"
            if role == self.active_role:
                pane.add_class("active-pane")
            else:
                pane.remove_class("active-pane")
            pane.styles.display = (
                "block" if mode != "single" or role == self.active_role else "none"
            )

        if mode != self.layout_mode:
            self.layout_mode = mode
            self.update_status(self.active_status())
            self.schedule_resize()

    def update_status(self, message: str) -> None:
        self.last_status = message
        if self.is_running:
            self.query_one("#status-message", Static).update(
                f"{self.task_id} · {message}"
            )

    def poll_state(self) -> None:
        state = load_state(self.args.state_file)
        record = state.get(self.task_id)
        if not isinstance(record, dict):
            return

        if record.get("status") == "paused":
            self.update_status("One implementer/reviewer round complete")
            self.exit()
            return

        if record.get("phase") == "reviewer":
            self.launch_role("reviewer")

    def poll_children(self) -> None:
        for session in self.sessions.values():
            if session.exited:
                continue
            try:
                pid, _status = os.waitpid(session.pid, os.WNOHANG)
            except ChildProcessError:
                pid = session.pid
            if pid == session.pid:
                session.exited = True
                try:
                    if self.event_loop is not None:
                        self.event_loop.remove_reader(session.master_fd)
                except (NotImplementedError, ValueError):
                    pass
                state = load_state(self.args.state_file)
                record = state.get(self.task_id)
                if (
                    session.role == "implementer"
                    and isinstance(record, dict)
                    and record.get("phase") == "reviewer"
                ):
                    session.pane.show_message("Igor idle · waiting for Rufus review")
                elif (
                    session.role == "reviewer"
                    and isinstance(record, dict)
                    and record.get("status") == "paused"
                ):
                    session.pane.show_message("Rufus idle · review round complete")
                if session.role == self.active_role:
                    if not isinstance(record, dict) or record.get("status") != "paused":
                        self.update_status(
                            f"{session.role.title()} ended; use resume to continue"
                        )
                        self.exit()

    def on_key(self, event: Any) -> None:
        key = event.key
        if key == "ctrl+q":
            self.exit()
            event.stop()
            return
        if key == "tab":
            roles = ("implementer", "reviewer")
            index = roles.index(self.active_role)
            self.active_role = roles[(index + 1) % 2]
            self.update_layout()
            self.update_status(self.active_status())
            event.stop()
            return
        special_keys = {
            "enter": b"\r",
            "backspace": b"\x7f",
            "delete": b"\x1b[3~",
            "up": b"\x1b[A",
            "down": b"\x1b[B",
            "right": b"\x1b[C",
            "left": b"\x1b[D",
            "home": b"\x1b[H",
            "end": b"\x1b[F",
            "pageup": b"\x1b[5~",
            "pagedown": b"\x1b[6~",
            "escape": b"\x1b",
            "shift+tab": b"\x1b[Z",
        }
        data = (
            event.character.encode()
            if event.character
            and key
            in {
                "tab",
                "shift+tab",
            }
            else special_keys.get(key)
        )
        if data is None and key.startswith("ctrl+") and len(key) == 6:
            data = bytes([ord(key[-1].upper()) - ord("@")])
        if data is None and event.character:
            data = event.character.encode()
        if data:
            self.write_active(data)
            event.stop()

    def on_paste(self, event: Paste) -> None:
        self.write_active(event.text.encode())
        event.stop()

    def on_click(self, event: Click) -> None:
        widget = event.widget
        role = getattr(widget, "id", None)
        while role not in {"implementer", "reviewer"} and widget is not None:
            widget = getattr(widget, "parent", None)
            role = getattr(widget, "id", None)
        if role in {"implementer", "reviewer"}:
            self.active_role = role
            self.update_layout()
            self.resize_sessions()
            self.schedule_resize()
            self.update_status(self.active_status())
            event.stop()

    async def action_quit(self) -> None:
        self.exit()

    def on_unmount(self) -> None:
        for session in self.sessions.values():
            try:
                if self.event_loop is not None:
                    self.event_loop.remove_reader(session.master_fd)
            except (NotImplementedError, ValueError):
                pass
            if not session.exited:
                try:
                    os.killpg(session.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            try:
                os.close(session.master_fd)
            except OSError:
                pass


def run_app(args: argparse.Namespace, task_id: str) -> None:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise SystemExit("begin/resume must be run from an interactive terminal")
    app = OrcApp(args, task_id)
    app.run()
    print(f"{task_id} orchestration ended")


def begin(args: argparse.Namespace) -> None:
    target_directory = normalize_target_directory(args.directory)
    state = load_state(args.state_file)
    if args.task_id in state:
        raise SystemExit(f"task already exists: {args.task_id}")

    state[args.task_id] = {
        "status": "active",
        "phase": "implementer",
        "round": 0,
        "prompt": args.prompt,
        "target_directory": str(target_directory),
        "implementer_id": None,
        "reviewer_id": None,
        "user_requests": [],
        "last_reviewer_event": None,
        "reviewer_reported_complete": False,
        "handoffs": [],
    }
    save_state(args.state_file, state)
    run_app(args, args.task_id)


def resume(args: argparse.Namespace) -> None:
    target_directory = normalize_target_directory(args.directory)
    state = load_state(args.state_file)
    record = state.get(args.task_id)
    if not isinstance(record, dict):
        raise SystemExit(f"unknown task: {args.task_id}")

    stored_target = record.get("target_directory")
    if not isinstance(stored_target, str) or not stored_target:
        raise SystemExit(
            f"task {args.task_id} has no stored target directory; begin a new task"
        )
    if Path(stored_target) != target_directory:
        raise SystemExit(
            f"target directory does not match task {args.task_id}: "
            f"stored {stored_target}, received {target_directory}"
        )

    requests = record.get("user_requests")
    if requests is None:
        requests = record.pop("user_feedback", [])
        record["user_requests"] = requests
    if not isinstance(requests, list):
        raise SystemExit(f"Orc state for {args.task_id} has invalid user_requests")
    requests.append(args.prompt)
    record["last_user_request"] = args.prompt
    record["status"] = "active"
    record["phase"] = "implementer"
    record["round"] = int(record.get("round", 0)) + 1
    save_state(args.state_file, state)
    run_app(args, args.task_id)


def idle_hook(args: argparse.Namespace) -> None:
    raw_payload = args.payload if args.payload is not None else sys.stdin.read()
    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError as error:
        raise SystemExit(f"invalid Codex idle-hook payload: {error}") from error

    task_id = os.environ.get("ORC_TASK_ID")
    role = os.environ.get("ORC_ROLE")
    session_id = session_id_from_payload(payload)
    state = load_state(args.state_file)

    if task_id is None or role not in {"implementer", "reviewer"}:
        task_id, role = find_task_role(state, session_id)
    if task_id is None or role is None:
        raise SystemExit("idle hook could not identify the Orc task and role")

    record = state.get(task_id)
    if not isinstance(record, dict):
        raise SystemExit(f"idle hook found no state for task {task_id}")
    target_value = record.get("target_directory")
    if not isinstance(target_value, str) or not target_value:
        raise SystemExit(
            f"idle hook found no valid target directory for task {task_id}"
        )
    target_directory = normalize_target_directory(Path(target_value))
    if session_id:
        record[f"{role}_id"] = session_id
    handoff_thread_id = session_id
    if handoff_thread_id is None:
        saved_thread_id = record.get(f"{role}_id")
        if isinstance(saved_thread_id, str) and saved_thread_id:
            handoff_thread_id = saved_thread_id
    record["last_idle_role"] = role
    record["last_idle_event"] = payload

    handoff = {
        "time": datetime.now(UTC).isoformat(timespec="seconds"),
        "local_time": datetime.now().astimezone().isoformat(timespec="seconds"),
        "task_id": task_id,
        "role": role,
        "round": record.get("round", 0),
        "thread_id": handoff_thread_id,
        "target_directory": str(target_directory),
        "commit": current_commit(target_directory),
        "message": assistant_message_from_payload(payload),
    }
    handoffs = record.setdefault("handoffs", [])
    if not isinstance(handoffs, list):
        handoffs = []
        record["handoffs"] = handoffs
    handoffs.append(handoff)
    record["last_handoff"] = handoff

    if role == "implementer":
        record["phase"] = "reviewer"
        save_state(args.state_file, state)
        return

    record["last_reviewer_event"] = payload
    record["status"] = "paused"
    record["reviewer_reported_complete"] = "TASK COMPLETE" in json.dumps(payload)
    save_state(args.state_file, state)


def find_task_role(
    state: dict[str, Any], session_id: str | None
) -> tuple[str | None, str | None]:
    if session_id is None:
        return None, None
    for task_id, record in state.items():
        if not isinstance(record, dict):
            continue
        for role in ("implementer", "reviewer"):
            if record.get(f"{role}_id") == session_id:
                return task_id, role
    return None, None


def main() -> None:
    args = parse_args()
    if args.command == "begin":
        begin(args)
    elif args.command == "resume":
        resume(args)
    else:
        idle_hook(args)


if __name__ == "__main__":
    main()
