#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pyte>=0.8.2",
#   "rich>=13.0",
#   "textual>=1.0.0",
# ]
# ///
"""Orchestrate interactive Igor and Rufus sessions in one terminal."""

from __future__ import annotations

import argparse
import asyncio
import errno
import fcntl
import json
import os
import re
import signal
import struct
import subprocess
import sys
import termios
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pyte
from rich.style import Style
from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Container
from textual.events import Click, MouseDown, MouseRelease, MouseUp, Paste
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
AGENTBOX_IDENTITY = Path("/etc/agentbox/identity")
CODEX_AGENTBOX_FLAG = "--dangerously-bypass-approvals-and-sandbox"
CLAUDE_AGENTBOX_FLAG = "--dangerously-skip-permissions"
DEFAULT_CLAUDE_COMMAND = "claude"
CLAUDE_REQUIRED_HELP = (
    "--print",
    "--output-format",
    "stream-json",
    "--input-format",
    "text",
    "--resume",
)
FOCUS_STATUS = "Ctrl-Q exits"
STATUS_SEGMENT_SEPARATOR = " · "
STATUS_VERSION_SEPARATOR = " "
STATUS_COLORS = {
    "task:active": "#7ee787",
    "task:completed": "#7ee787",
    "task:paused": "#f2cc60",
    "task:blocked": "#f2cc60",
    "task:stopped": "#f2cc60",
    "role:inactive": "#8b949e",
    "role:not started": "#8b949e",
    "role:active": "#7ee787",
    "role:waiting": "#8b949e",
    "role:failed": "#ff7b72",
    "backend": "#ffffff",
    "agentbox": "#ff7b72",
}
STATUS_SEGMENT_IDS = (
    "status-message",
    "status-igor",
    "status-rufus",
    "status-backend",
    "status-agentbox",
    "status-hint",
)
UNABLE_TO_PROCEED = "UNABLE_TO_PROCEED"
DEFAULT_MAX_ROUNDS = 5
DEFAULT_DEADLINE_SECONDS = 60 * 60
VALID_STOP_REASONS = {
    "completion",
    "clarification",
    "deadline",
    "max_rounds",
    "child_failure",
    "manual_pause",
}
TERMINAL_TASK_STATUSES = {"paused", "blocked", "stopped", "completed"}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Orchestrate Igor and Rufus sessions. "
            "Usage: begin DIRECTORY TASK-ID [PROMPT] [limits] or "
            "resume TASK-ID PROMPT."
        ),
        epilog=(
            "On Linux, /etc/agentbox/identity enables the selected backend's "
            "external-sandbox mode. The marker is detected by file existence only."
        ),
    )
    parser.add_argument(
        "--state-file",
        type=Path,
        default=Path.home() / ".orc" / "codex-state.json",
        help="Path for Orc state (default: %(default)s).",
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
    begin.add_argument(
        "prompt",
        nargs="?",
        default="",
        help="Optional initial request for Igor.",
    )
    backend = begin.add_mutually_exclusive_group()
    backend.add_argument(
        "--codex",
        dest="backend_selector",
        action="store_const",
        const="codex",
        help="Use the Codex backend.",
    )
    backend.add_argument(
        "--claude",
        dest="backend_selector",
        action="store_const",
        const="claude",
        help="Use the Claude backend.",
    )
    begin.add_argument(
        "--max-rounds",
        type=int,
        default=None,
        help="Automatic cycle limit, from 1 through 5 (default: 5).",
    )
    begin.add_argument(
        "--deadline-minutes",
        type=int,
        default=None,
        help="Automatic wall-clock limit, from 1 through 1440 minutes (default: 60).",
    )

    resume = commands.add_parser(
        "resume", help="Resume a task in its persisted target directory."
    )
    resume.add_argument("task_id", help="Task identifier, such as TASK-001.")
    resume.add_argument(
        "prompt",
        help="Follow-up or new request for Igor in this task context.",
    )

    hook = commands.add_parser("idle-hook", help=argparse.SUPPRESS)
    hook.add_argument("payload", nargs="?")

    args = parser.parse_args(argv)
    if args.command == "begin":
        max_rounds = DEFAULT_MAX_ROUNDS if args.max_rounds is None else args.max_rounds
        deadline_minutes = (
            60 if args.deadline_minutes is None else args.deadline_minutes
        )
        if not 1 <= max_rounds <= DEFAULT_MAX_ROUNDS:
            parser.error("--max-rounds must be an integer from 1 through 5")
        if not 1 <= deadline_minutes <= 1440:
            parser.error("--deadline-minutes must be an integer from 1 through 1440")
        args.max_rounds = max_rounds
        args.deadline_minutes = deadline_minutes
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


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_now() -> str:
    return utc_now().isoformat(timespec="seconds")


def parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def payload_field(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        if key in value:
            return value[key]
        for nested in value.values():
            found = payload_field(nested, key)
            if found is not None:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = payload_field(nested, key)
            if found is not None:
                return found
    return None


def message_field(message: str | None, key: str) -> str | None:
    if not message:
        return None
    match = re.search(
        rf"^\s*{re.escape(key)}\s*:\s*(.+?)\s*$",
        message,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    return match.group(1).strip() if match else None


def handoff_status(payload: Any) -> str | None:
    value = payload_field(payload, "status")
    message = assistant_message_from_payload(payload)
    if value is None:
        value = message_field(message, "status")
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().upper().replace("-", "_")
    if normalized == UNABLE_TO_PROCEED:
        return UNABLE_TO_PROCEED
    if normalized in {"COMPLETE", "COMPLETED", "TASK_COMPLETE", "TASK COMPLETE"}:
        return "COMPLETE"
    # Only the blocker status has special control semantics. Other non-empty
    # statuses are ordinary handoff metadata and must not stop the workflow.
    return normalized


def handoff_reason(payload: Any) -> str | None:
    message = assistant_message_from_payload(payload)
    for key in ("reason", "blocker_reason", "blockers", "blocker"):
        value = payload_field(payload, key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        value = message_field(message, key)
        if value:
            return value
    return None


def handoff_event_key(task_id: str, role: str, payload: Any) -> str:
    try:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        encoded = repr(payload)
    return f"{task_id}:{role}:{encoded}"


def handoff_details(payload: Any) -> dict[str, Any]:
    message = assistant_message_from_payload(payload)
    details: dict[str, Any] = {}
    for key in ("summary", "files", "verification", "blockers", "requested_action"):
        value = payload_field(payload, key)
        if value is None:
            value = message_field(message, key)
        if value is not None:
            details[key] = value
    return details


def deadline_expired(record: dict[str, Any], now: datetime | None = None) -> bool:
    if not record.get("automatic_rounds"):
        return False
    deadline = parse_timestamp(record.get("deadline_at"))
    return deadline is not None and (now or utc_now()) >= deadline


def set_stop_reason(
    record: dict[str, Any], reason: str, *, completed: bool = False
) -> None:
    if reason not in VALID_STOP_REASONS:
        raise ValueError(f"unknown Orc stop reason: {reason}")
    record["status"] = (
        "completed"
        if completed
        else ("blocked" if reason == "clarification" else "stopped")
    )
    record["phase"] = (
        "complete"
        if completed
        else ("blocked" if reason == "clarification" else "stopped")
    )
    record["stop_reason"] = reason


def reviewer_prompt(record: dict[str, Any]) -> str:
    requests = [record.get("prompt")]
    requests.extend(record.get("user_requests", []))
    requests = [
        request for request in requests if isinstance(request, str) and request.strip()
    ]
    target = record.get("target_directory", "unknown")
    prompt = (
        f"{REVIEWER_PROMPT}\n\n"
        f"Target project directory: {target}\n"
        "Review the target project's current worktree and Git repository. "
        "Do not review or modify Orc's repository.\n"
        "Igor has completed the implementation turn. Review the current "
        "worktree now. Do not implement fixes. Report findings and evidence, "
        "or report exactly TASK COMPLETE when ready."
    )
    if requests:
        prompt += "\n\nUser requests in this context:\n"
        prompt += "\n".join(f"- {request}" for request in requests)
    return prompt


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


def add_agentbox_codex_flag(command: list[str]) -> list[str]:
    """Add the agentbox Codex mode flag once when running inside agentbox."""

    if (
        sys.platform == "linux"
        and AGENTBOX_IDENTITY.exists()
        and CODEX_AGENTBOX_FLAG not in command
    ):
        command.insert(max(len(command) - 1, 1), CODEX_AGENTBOX_FLAG)
    return command


def add_agentbox_claude_flag(command: list[str]) -> list[str]:
    """Add Claude's agentbox permission mode once when running in agentbox."""

    if (
        sys.platform == "linux"
        and AGENTBOX_IDENTITY.exists()
        and CLAUDE_AGENTBOX_FLAG not in command
    ):
        # The prompt is always the final argument. Keep the permission flag
        # among the CLI options so a prompt beginning with a dash is still
        # treated as input text by Claude Code.
        command.insert(max(len(command) - 1, 1), CLAUDE_AGENTBOX_FLAG)
    return command


def backend_command_value(value: Any) -> list[str]:
    """Normalize a configured executable without invoking a shell."""

    if isinstance(value, str) and value:
        return [value]
    if (
        isinstance(value, list)
        and value
        and all(isinstance(item, str) and item for item in value)
    ):
        return list(value)
    raise SystemExit("backend command must be a non-empty executable")


def codex_command() -> list[str]:
    return backend_command_value(os.environ.get("CODEX_COMMAND", "codex"))


def claude_command() -> list[str]:
    return backend_command_value(
        os.environ.get("ORC_CLAUDE_COMMAND", DEFAULT_CLAUDE_COMMAND)
    )


def probe_claude(command: list[str]) -> str:
    """Verify Claude Code's print/stream/resume capability contract."""

    try:
        result = subprocess.run(
            [*command, "--help"],
            capture_output=True,
            check=False,
            text=True,
        )
    except OSError as error:
        raise SystemExit(
            f"cannot run Claude backend {command[0]!r} for capability check: {error}"
        ) from error
    help_text = f"{result.stdout}\n{result.stderr}"
    missing = [flag for flag in CLAUDE_REQUIRED_HELP if flag not in help_text]
    if result.returncode != 0 or missing:
        detail = ", ".join(missing) if missing else f"exit status {result.returncode}"
        raise SystemExit(
            f"Claude backend {command[0]!r} is incompatible; "
            f"--help must expose print stream/resume support (missing {detail})"
        )

    # Version is useful state, but it is intentionally best-effort: the
    # capability contract is established by --help and some wrappers do not
    # implement --version.
    try:
        version = subprocess.run(
            [*command, "--version"],
            capture_output=True,
            check=False,
            text=True,
        )
    except OSError:
        return "unknown"
    value = (version.stdout or version.stderr).strip().splitlines()
    return value[0][:200] if value else "unknown"


def backend_from_record(record: dict[str, Any]) -> str:
    backend = record.get("backend")
    if backend not in {"codex", "claude"}:
        raise SystemExit(
            "task state has no valid backend; resume requires persisted "
            "backend codex or claude"
        )
    return str(backend)


def selected_backend(args: argparse.Namespace) -> str:
    selector = getattr(args, "backend_selector", None)
    if selector in {"codex", "claude"}:
        return selector
    configured = os.environ.get("ORC_BACKEND", "").strip()
    if configured in {"codex", "claude"}:
        return configured
    raise SystemExit(
        "select a backend with --codex or --claude, or set "
        "ORC_BACKEND to codex or claude"
    )


def valid_round_limit(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        limit = int(value)
    except (TypeError, ValueError):
        return None
    return limit if 1 <= limit <= DEFAULT_MAX_ROUNDS else None


def valid_deadline_seconds(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return None
    return seconds if 60 <= seconds <= 1440 * 60 else None


def current_round(record: dict[str, Any]) -> int:
    value = record.get("round", 1)
    try:
        return max(int(value), 1)
    except (TypeError, ValueError):
        return 1


def workflow_active_role(record: dict[str, Any]) -> str | None:
    if record.get("status") != "active":
        return None
    phase = record.get("phase")
    return phase if phase in {"implementer", "reviewer"} else None


def stored_backend_command(record: dict[str, Any], backend: str) -> list[str]:
    value = record.get("backend_command")
    if value is None:
        return claude_command() if backend == "claude" else codex_command()
    return backend_command_value(value)


def claude_session_for_role(record: dict[str, Any], role: str) -> str | None:
    sessions = record.get("claude_sessions")
    if isinstance(sessions, dict):
        value = sessions.get(role)
        if isinstance(value, str) and value:
            return value
    value = record.get(f"{role}_id")
    if isinstance(value, str) and value:
        return value
    return None


def child_exit_code(status: int) -> int:
    try:
        return os.waitstatus_to_exitcode(status)
    except (AttributeError, ValueError):
        return status


def backend_launch_command(
    backend: str,
    configured_command: list[str],
    prompt: str,
    task_id: str,
    role: str,
    thread_id: Any,
    has_request: bool,
    automatic: bool,
    state_file: Path,
) -> list[str]:
    """Build an argv list for either backend without shell interpretation."""

    if backend == "claude":
        command = [
            *configured_command,
            "--print",
            "--output-format",
            "stream-json",
            "--input-format",
            "text",
        ]
        if isinstance(thread_id, str) and thread_id:
            if not has_request and not automatic:
                raise SystemExit(
                    f"cannot resume {role}: no user request recorded for task {task_id}"
                )
            command.extend(["--resume", thread_id])
        full_prompt = (
            prompt
            + f"\n\nTask ID: {task_id}\n"
            + f"Session name: {session_name(task_id, role)}"
        )
        command.append(full_prompt)
        return add_agentbox_claude_flag(command)

    command = list(configured_command)
    # General Orc testing can keep the agent session in place by setting
    # ORC_DISABLE_IDLE_HOOK=1 for this launch.
    if os.environ.get("ORC_DISABLE_IDLE_HOOK") != "1":
        command.extend(
            [
                "-c",
                f"notify={notify_config(state_file)}",
            ]
        )
    if isinstance(thread_id, str) and thread_id:
        if not has_request and not automatic:
            raise SystemExit(
                f"cannot resume {role}: no user request recorded for task {task_id}"
            )
        command.extend(["resume", thread_id, prompt])
    else:
        full_prompt = (
            f"{prompt}\n\nTask ID: {task_id}\n"
            f"Session name: {session_name(task_id, role)}"
        )
        command.append(full_prompt)
    return add_agentbox_codex_flag(command)


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
    backend: str = "codex"
    stream_buffer: str = ""
    stream_events: list[dict[str, Any]] | None = None
    session_id: str | None = None
    final_response: str | None = None
    stream_error: str | None = None
    exited: bool = False
    retired: bool = False
    handoff_count: int = 0
    command: list[str] | None = None

    def __post_init__(self) -> None:
        if self.stream_events is None:
            self.stream_events = []


class OrcApp(App[None]):
    """Own the terminal and multiplex the two agent backend PTYs."""

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
        overflow: hidden;
    }

    #status-left {
        width: 1fr;
        height: 1;
        layout: horizontal;
        overflow: hidden;
    }

    .status-segment {
        width: auto;
        height: 1;
        padding: 0 1;
        content-align: left middle;
        overflow: hidden;
        text-wrap: nowrap;
    }

    #status-version {
        width: 11;
        height: 1;
        padding: 0 0 0 1;
        content-align: left middle;
        text-wrap: nowrap;
    }

    """

    def __init__(self, args: argparse.Namespace, task_id: str) -> None:
        super().__init__()
        self.args = args
        self.task_id = task_id
        self.sessions: dict[str, ChildSession] = {}
        self.retired_sessions: list[ChildSession] = []
        self.started_roles: set[str] = set()
        self.active_role: str | None = "implementer"
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
            Container(
                Static(
                    f"{self.task_id}: starting · round 1/5",
                    id="status-message",
                    classes="status-segment",
                    markup=False,
                ),
                Static(
                    "Igor: not started",
                    id="status-igor",
                    classes="status-segment",
                    markup=False,
                ),
                Static(
                    "Rufus: not started",
                    id="status-rufus",
                    classes="status-segment",
                    markup=False,
                ),
                Static(
                    "backend: codex",
                    id="status-backend",
                    classes="status-segment",
                    markup=False,
                ),
                Static(
                    "agentbox: no-permissions",
                    id="status-agentbox",
                    classes="status-segment",
                    markup=False,
                ),
                Static(
                    FOCUS_STATUS,
                    id="status-hint",
                    classes="status-segment",
                    markup=False,
                ),
                id="status-left",
            ),
            Static(ORC_VERSION, id="status-version", markup=False),
            id="status",
        )

    @staticmethod
    def initial_role(record: dict[str, Any]) -> str:
        phase = record.get("phase")
        return phase if phase in {"implementer", "reviewer"} else "implementer"

    def active_workflow_role(self, record: dict[str, Any]) -> str | None:
        role = workflow_active_role(record)
        self.active_role = role
        return role

    def on_mount(self) -> None:
        if os.name != "posix":
            self.fatal_error("Orc's interactive PTY UI currently requires POSIX.")
            return
        self.event_loop = asyncio.get_running_loop()
        self.set_interval(0.1, self.poll_state)
        self.set_interval(0.1, self.poll_children)
        self.update_layout()
        state = load_state(self.args.state_file)
        record = state.get(self.task_id)
        initial_role = (
            self.initial_role(record) if isinstance(record, dict) else "implementer"
        )
        self.call_after_refresh(self.launch_role, initial_role)

    def fatal_error(self, message: str) -> None:
        self.last_status = message
        self.exit()

    def pane(self, role: str) -> SessionPane:
        return self.query_one(f"#{role}", SessionPane)

    def _handoffs_for_role(
        self, record: dict[str, Any], role: str
    ) -> list[dict[str, Any]]:
        handoffs = record.get("handoffs", [])
        if not isinstance(handoffs, list):
            return []
        return [
            handoff
            for handoff in handoffs
            if isinstance(handoff, dict) and handoff.get("role") == role
        ]

    def role_state(self, record: dict[str, Any], role: str) -> str:
        """Derive the display state for one role from workflow evidence."""

        failure = record.get("child_failure")
        if isinstance(failure, dict) and failure.get("role") == role:
            return "failed"

        if record.get("status") == "completed" or record.get("phase") == "complete":
            return "inactive"

        if workflow_active_role(record) == role:
            return "active"

        if record.get("status") != "active":
            return "waiting" if self._handoffs_for_role(record, role) else "inactive"

        session = self.sessions.get(role)
        if (
            session is not None
            and not session.exited
            and not getattr(session, "retired", False)
        ):
            handoffs = record.get("handoffs", [])
            handoff_count = len(handoffs) if isinstance(handoffs, list) else 0
            session_handoff_count = getattr(session, "handoff_count", handoff_count)
            if handoff_count > session_handoff_count and any(
                isinstance(handoff, dict) and handoff.get("role") == role
                for handoff in handoffs[session_handoff_count:]
            ):
                return "waiting"
            return "waiting"

        if self._handoffs_for_role(record, role):
            return "waiting"

        return "not started"

    def agentbox_enabled(self, record: dict[str, Any]) -> bool:
        if sys.platform != "linux" or not AGENTBOX_IDENTITY.exists():
            return False
        backend = record.get("backend")
        if backend not in {"codex", "claude"}:
            return False
        expected = CODEX_AGENTBOX_FLAG if backend == "codex" else CLAUDE_AGENTBOX_FLAG
        phase = record.get("phase")
        session = self.sessions.get(phase) if isinstance(phase, str) else None
        command = (
            getattr(session, "command", None)
            if session is not None
            else record.get("launch_command")
        )
        return isinstance(command, list) and expected in command

    @staticmethod
    def _status_color(kind: str, value: str) -> str:
        return STATUS_COLORS.get(f"{kind}:{value}", "#d0d7de")

    def status_segments(self, record: dict[str, Any]) -> dict[str, str]:
        """Return the status bar's ordered, human-readable segments."""

        backend = record.get("backend")
        if backend not in {"codex", "claude"}:
            backend = "unknown"
        maximum = valid_round_limit(record.get("max_rounds")) or DEFAULT_MAX_ROUNDS
        segments = {
            "task": (
                f"{self.task_id}: {record.get('status', 'unknown')} · "
                f"round {current_round(record)}/{maximum}"
            ),
            "igor": f"Igor: {self.role_state(record, 'implementer')}",
            "rufus": f"Rufus: {self.role_state(record, 'reviewer')}",
            "backend": f"backend: {backend}",
            "hint": FOCUS_STATUS,
        }
        if self.agentbox_enabled(record):
            segments["agentbox"] = "agentbox: no-permissions"
        return segments

    def status_text(self, record: dict[str, Any]) -> str:
        segments = self.status_segments(record)
        ordered = [segments[key] for key in ("task", "igor", "rufus", "backend")]
        if "agentbox" in segments:
            ordered.append(segments["agentbox"])
        ordered.extend((segments["hint"], ORC_VERSION))
        return STATUS_SEGMENT_SEPARATOR.join(ordered)

    @staticmethod
    def _status_text(value: str, color: str) -> Text:
        separator = value.find(": ")
        if separator < 0:
            return Text(value, style=Style(color="#d0d7de"))
        label_end = separator + 2
        rendered = Text(value[:label_end], style=Style(color="#d0d7de"))
        rendered.append(value[label_end:], style=Style(color=color))
        return rendered

    def _status_width(self) -> int:
        size = getattr(self, "size", None)
        width = getattr(size, "width", 0)
        return max(width, 0)

    @staticmethod
    def _status_padding(width: int, segments: dict[str, str]) -> int:
        # Separators provide the visual gutter. Keeping CSS padding at zero
        # lets the width calculation reserve those cells explicitly.
        return 0

    def _visible_status_keys(
        self, segments: dict[str, str], width: int
    ) -> tuple[set[str], str]:
        """Select complete segments that fit before the fixed version rail."""

        left_width = max(width - len(STATUS_VERSION_SEPARATOR + ORC_VERSION), 0)
        visible: list[str] = ["task", "igor", "rufus"]

        def cost(keys: list[str]) -> int:
            separators = max(len(keys) - 1, 0) * len(STATUS_SEGMENT_SEPARATOR)
            return sum(len(segments[key]) for key in keys) + separators

        # Keep the warning ahead of the redundant backend label under
        # constrained widths, while preserving the documented logical order.
        optional = (
            ["agentbox", "backend"] if "agentbox" in segments else ["backend"]
        )
        for key in optional:
            if cost(visible + [key]) <= left_width:
                visible.append(key)
        if "agentbox" in segments and "agentbox" not in visible:
            # It is the only optional diagnostic worth displacing the backend
            # for, so try it explicitly when the backend consumed the rail.
            candidate = [key for key in visible if key != "backend"] + ["agentbox"]
            if cost(candidate) <= left_width:
                visible = candidate
        if cost(visible + ["hint"]) <= left_width:
            visible.append("hint")
        return set(visible), segments["hint"] if "hint" in visible else ""

    def render_status_bar(self, record: dict[str, Any]) -> None:
        """Render composed, styled segments and the fixed version rail."""

        segments = self.status_segments(record)
        width = self._status_width()
        visible, hint = self._visible_status_keys(segments, width)
        padding = self._status_padding(width, segments)
        task_color = self._status_color(
            "task", str(record.get("status", "unknown"))
        )
        values = {
            "status-message": (segments["task"], task_color),
            "status-igor": (
                segments["igor"],
                self._status_color("role", self.role_state(record, "implementer")),
            ),
            "status-rufus": (
                segments["rufus"],
                self._status_color("role", self.role_state(record, "reviewer")),
            ),
            "status-backend": (segments["backend"], STATUS_COLORS["backend"]),
            "status-agentbox": (
                segments.get("agentbox", ""),
                STATUS_COLORS["agentbox"],
            ),
            "status-hint": (hint, "#d0d7de"),
        }
        visible_order = ("task", "igor", "rufus", "backend", "agentbox", "hint")
        shown_keys = [
            key
            for key in visible_order
            if key in visible or (key == "hint" and bool(hint))
        ]
        separator_keys = set(shown_keys[1:])
        remaining_width = max(
            width - len(STATUS_VERSION_SEPARATOR + ORC_VERSION), 0
        )
        for widget_id in STATUS_SEGMENT_IDS:
            try:
                widget = self.query_one(f"#{widget_id}", Static)
            except Exception:
                continue
            value, color = values[widget_id]
            key = {
                "status-message": "task",
                "status-igor": "igor",
                "status-rufus": "rufus",
                "status-backend": "backend",
                "status-agentbox": "agentbox",
                "status-hint": "hint",
            }[widget_id]
            if key in separator_keys and value:
                value = f"{STATUS_SEGMENT_SEPARATOR}{value}"
            widget.update(self._status_text(value, color))
            styles = getattr(widget, "styles", None)
            if styles is not None and hasattr(styles, "display"):
                shown = key in visible or (key == "hint" and bool(hint))
                segment_width = min(len(value), remaining_width) if shown else 0
                remaining_width -= segment_width
                if hasattr(styles, "padding"):
                    styles.padding = (0, padding // 2)
                if hasattr(styles, "width"):
                    styles.width = segment_width
                styles.display = "block" if shown and segment_width else "none"
        try:
            version = self.query_one("#status-version", Static)
        except Exception:
            version = None
        if version is not None:
            version.update(
                self._status_text(
                    f"{STATUS_VERSION_SEPARATOR}{ORC_VERSION}", "#d0d7de"
                )
            )

    def refresh_status(self) -> None:
        state = load_state(self.args.state_file)
        record = state.get(self.task_id)
        if isinstance(record, dict):
            rendered = self.status_text(record)
            self.update_status(rendered)

    def refresh_workflow_ui(self) -> None:
        """Recompute the active-agent border after persisted state changes."""

        if getattr(self, "_running", False):
            self.update_layout()
        else:
            self.refresh_status()

    def launch_role(self, role: str) -> None:
        existing = self.sessions.get(role)
        if (
            role in self.started_roles
            and existing is not None
            and not existing.exited
            and not getattr(existing, "retired", False)
        ):
            return
        state = load_state(self.args.state_file)
        record = state.get(self.task_id)
        if not isinstance(record, dict):
            self.fatal_error(f"no state for task {self.task_id}")
            return

        if record.get("status") in TERMINAL_TASK_STATUSES:
            return

        target_value = record.get("target_directory")
        if not isinstance(target_value, str) or not target_value:
            self.fatal_error(
                f"task {self.task_id} has no target directory in Orc state"
            )
            return
        target_directory = Path(target_value)
        if deadline_expired(record):
            set_stop_reason(record, "deadline")
            save_state(self.args.state_file, state)
            self.refresh_workflow_ui()
            return

        try:
            backend = backend_from_record(record)
        except SystemExit as error:
            self.fatal_error(str(error))
            return

        requests = record.get("user_requests", [])
        if not isinstance(requests, list):
            self.fatal_error(
                f"cannot launch {role}: invalid user requests for task {self.task_id}"
            )
            return
        has_request = isinstance(requests, list) and bool(requests)
        thread_id = record.get(f"{role}_id")
        if backend == "claude":
            thread_id = claude_session_for_role(record, role)
        if (
            isinstance(thread_id, str)
            and thread_id
            and not has_request
            and not record.get("automatic_rounds")
        ):
            self.fatal_error(
                f"cannot resume {role}: no user request recorded for task "
                f"{self.task_id}"
            )
            return
        auto_continuation = bool(record.get("automatic_rounds")) and bool(
            isinstance(thread_id, str) and thread_id
        )
        if role == "implementer" and record.get("round", 0) == 0:
            record["round"] = 1
        generations = record.get("role_generations", {})
        if not isinstance(generations, dict):
            generations = {}
        generation = int(generations.get(role, 0)) + 1
        generations[role] = generation
        record["role_generations"] = generations
        save_state(self.args.state_file, state)

        if role == "implementer":
            prompt = (
                IMPLEMENTER_ROUND_PROMPT
                if has_request or auto_continuation
                else IMPLEMENTER_PROMPT
            )
            prompt += (
                f"\n\nTarget project directory: {target_directory}\n"
                "Work in the target project; Orc's repository contains only "
                "the orchestrator state and UI."
            )
            prompt += "\n\n" + HANDOFF_PROMPT
            if has_request:
                prompt += "\n\nUser request for this context:\n"
                prompt += str(requests[-1])
            elif not auto_continuation and str(record.get("prompt", "")).strip():
                prompt += "\n\nUser request:\n" + str(record["prompt"])
        else:
            prompt = reviewer_prompt(record) + "\n\n" + HANDOFF_PROMPT

        if record.get("backend_command") is None:
            configured_command = (
                getattr(self.args, "codex", None) or codex_command()
                if backend == "codex"
                else claude_command()
            )
        else:
            configured_command = stored_backend_command(record, backend)
        command = backend_launch_command(
            backend,
            backend_command_value(configured_command),
            prompt,
            self.task_id,
            role,
            thread_id,
            bool(requests),
            bool(record.get("automatic_rounds")),
            self.args.state_file,
        )

        record["launch_command"] = command
        record["launch_backend"] = backend
        handoffs = record.get("handoffs", [])
        handoff_count = len(handoffs) if isinstance(handoffs, list) else 0
        save_state(self.args.state_file, state)

        environment = os.environ.copy()
        # The child is connected to Orc's ANSI-capable terminal emulator, not
        # directly to the caller's stdout.  Do not let a wrapper/container
        # level NO_COLOR setting disable Codex's screen colors in the pane.
        environment.pop("NO_COLOR", None)
        if not environment.get("TERM") or environment["TERM"] == "dumb":
            environment["TERM"] = "xterm-256color"
        environment["ORC_TASK_ID"] = self.task_id
        environment["ORC_ROLE"] = role
        environment["ORC_ROUND"] = str(record.get("round", 0))
        environment["ORC_ROLE_GENERATION"] = str(generation)
        environment["ORC_TARGET_DIRECTORY"] = str(target_directory)
        environment["ORC_BACKEND"] = backend
        environment["ORC_STATE_FILE"] = str(self.args.state_file)
        try:
            pid, master_fd = self.fork_codex(command, environment, target_directory)
        except OSError as error:
            self.fatal_error(f"could not launch {role}: {error}")
            return

        os.set_blocking(master_fd, False)
        pane = self.pane(role)
        pane.show_message(f"Starting {role.title()}…")
        session = ChildSession(
            role,
            pid,
            master_fd,
            pane,
            backend=backend,
            handoff_count=handoff_count,
            command=command,
        )
        self.sessions[role] = session
        self.started_roles.add(role)
        self.active_role = role
        self.update_layout()
        self.set_master_reader(session)
        self.resize_session(session)
        self.schedule_resize()
        self.refresh_status()

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
            if getattr(session, "backend", "codex") == "claude":
                self.read_claude_stream(session, data)

    @staticmethod
    def _claude_event_text(event: dict[str, Any]) -> str | None:
        result = event.get("result")
        if isinstance(result, str) and result:
            return result
        message = event.get("message")
        if isinstance(message, str) and message:
            return message
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str) and content:
                return content
            if isinstance(content, list):
                parts = []
                for item in content:
                    if isinstance(item, dict) and isinstance(item.get("text"), str):
                        parts.append(item["text"])
                if parts:
                    return "".join(parts)
        return None

    @classmethod
    def read_claude_stream(cls, session: ChildSession, data: bytes) -> None:
        session.stream_buffer += data.decode("utf-8", errors="replace")
        lines = session.stream_buffer.splitlines(keepends=True)
        if lines and not lines[-1].endswith(("\n", "\r")):
            session.stream_buffer = lines.pop()
        else:
            session.stream_buffer = ""
        for line in lines:
            try:
                value = json.loads(line.strip())
            except json.JSONDecodeError:
                # PTY output can contain terminal noise. Preserve it in the
                # pane, but only JSON objects participate in the backend
                # protocol.
                continue
            if not isinstance(value, dict):
                continue
            if session.stream_events is None:
                session.stream_events = []
            session.stream_events.append(value)
            session_id = session_id_from_payload(value)
            if session_id:
                session.session_id = session_id
            if value.get("is_error") is True or value.get("subtype") == "error":
                session.stream_error = cls._claude_event_text(value) or "Claude error"
            text = cls._claude_event_text(value)
            if text:
                session.final_response = text

    def drain_session(self, session: ChildSession) -> None:
        """Read output that arrived just before a child exited."""

        while True:
            try:
                data = os.read(session.master_fd, 65536)
            except BlockingIOError:
                return
            except OSError as error:
                if error.errno not in (errno.EIO, errno.EBADF):
                    self.update_status(f"{session.role.title()} PTY error: {error}")
                return
            if not data:
                return
            session.pane.feed(data)
            if getattr(session, "backend", "codex") == "claude":
                self.read_claude_stream(session, data)

    @staticmethod
    def claude_handoff(session: ChildSession) -> dict[str, Any] | None:
        events = session.stream_events or []
        if session.stream_buffer.strip():
            OrcApp.read_claude_stream(session, b"\n")
            events = session.stream_events or []
        if not session.session_id:
            for event in events:
                session.session_id = session_id_from_payload(event)
                if session.session_id:
                    break
        final_response = session.final_response
        for event in reversed(events):
            if event.get("type") == "result":
                result = event.get("result")
                if isinstance(result, str) and result:
                    final_response = result
                break
        if not session.session_id or not final_response or session.stream_error:
            return None
        payload: dict[str, Any] = {
            "session_id": session.session_id,
            "last-assistant-message": final_response,
        }
        status = handoff_status(payload)
        if status is None:
            return None
        return payload

    def handle_claude_exit(
        self,
        session: ChildSession,
        state: dict[str, Any],
        record: dict[str, Any],
        status: int,
    ) -> bool:
        """Turn a Claude stream's final message into the shared idle event."""

        if record.get("status") in TERMINAL_TASK_STATUSES:
            return True

        exit_code = child_exit_code(status)
        if exit_code != 0:
            record["child_failure"] = {
                "role": session.role,
                "backend": "claude",
                "exit_status": status,
                "reason": f"Claude exited with status {exit_code}",
                "time": iso_now(),
            }
            set_stop_reason(record, "child_failure")
            save_state(self.args.state_file, state)
            self.refresh_workflow_ui()
            return True

        payload = self.claude_handoff(session)
        if payload is None:
            record["child_failure"] = {
                "role": session.role,
                "backend": "claude",
                "exit_status": status,
                "reason": session.stream_error
                or "clean Claude exit without a valid handoff",
                "time": iso_now(),
            }
            set_stop_reason(record, "child_failure")
            save_state(self.args.state_file, state)
            self.refresh_workflow_ui()
            return True

        session_id = session.session_id
        if session_id:
            record["claude_session_id"] = session_id
            record["claude_final_response"] = session.final_response
            sessions = record.setdefault("claude_sessions", {})
            if not isinstance(sessions, dict):
                sessions = {}
                record["claude_sessions"] = sessions
            sessions[session.role] = session_id
            record[f"{session.role}_id"] = session_id
            save_state(self.args.state_file, state)

        previous_task = os.environ.get("ORC_TASK_ID")
        previous_role = os.environ.get("ORC_ROLE")
        previous_round = os.environ.get("ORC_ROUND")
        previous_generation = os.environ.get("ORC_ROLE_GENERATION")
        os.environ["ORC_TASK_ID"] = self.task_id
        os.environ["ORC_ROLE"] = session.role
        os.environ["ORC_ROUND"] = str(record.get("round", 0))
        generations = record.get("role_generations")
        if isinstance(generations, dict) and session.role in generations:
            os.environ["ORC_ROLE_GENERATION"] = str(generations[session.role])
        else:
            os.environ.pop("ORC_ROLE_GENERATION", None)
        try:
            idle_hook(
                argparse.Namespace(
                    state_file=self.args.state_file,
                    payload=json.dumps(payload),
                )
            )
        except SystemExit as error:
            record["child_failure"] = {
                "role": session.role,
                "backend": "claude",
                "exit_status": status,
                "reason": str(error),
                "time": iso_now(),
            }
            set_stop_reason(record, "child_failure")
            save_state(self.args.state_file, state)
            self.refresh_workflow_ui()
        finally:
            if previous_task is None:
                os.environ.pop("ORC_TASK_ID", None)
            else:
                os.environ["ORC_TASK_ID"] = previous_task
            if previous_role is None:
                os.environ.pop("ORC_ROLE", None)
            else:
                os.environ["ORC_ROLE"] = previous_role
            if previous_round is None:
                os.environ.pop("ORC_ROUND", None)
            else:
                os.environ["ORC_ROUND"] = previous_round
            if previous_generation is None:
                os.environ.pop("ORC_ROLE_GENERATION", None)
            else:
                os.environ["ORC_ROLE_GENERATION"] = previous_generation
        return True

    def write_active(self, data: bytes) -> None:
        state = load_state(self.args.state_file)
        record = state.get(self.task_id)
        if not isinstance(record, dict):
            return
        role = workflow_active_role(record)
        if role is None:
            self.active_role = None
            return
        self.active_role = role
        session = self.sessions.get(role)
        if session is None or session.exited:
            return
        try:
            os.write(session.master_fd, data)
        except OSError as error:
            if error.errno not in (errno.EPIPE, errno.EBADF):
                self.update_status(f"could not write to {session.role}: {error}")

    def retire_session(self, session: ChildSession) -> None:
        """Stop a child after a normal handoff without treating it as a failure."""

        if getattr(session, "retired", False) or session.exited:
            return
        session.retired = True
        try:
            if self.event_loop is not None:
                self.event_loop.remove_reader(session.master_fd)
        except (NotImplementedError, ValueError):
            pass
        try:
            os.killpg(session.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except OSError:
            try:
                os.kill(session.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        retired_sessions = getattr(self, "retired_sessions", None)
        if retired_sessions is None:
            retired_sessions = []
            self.retired_sessions = retired_sessions
        retired_sessions.append(session)
        if self.sessions.get(session.role) is session:
            del self.sessions[session.role]

    def retire_completed_sessions(self, record: dict[str, Any]) -> None:
        handoffs = record.get("handoffs", [])
        if not isinstance(handoffs, list):
            return
        for session in list(self.sessions.values()):
            if session.exited or getattr(session, "retired", False):
                continue
            handoff_count = getattr(session, "handoff_count", 0)
            new_handoffs = handoffs[handoff_count:]
            if any(
                isinstance(handoff, dict) and handoff.get("role") == session.role
                for handoff in new_handoffs
            ):
                self.retire_session(session)

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
        args = getattr(self, "args", None)
        if args is None or not hasattr(args, "state_file"):
            return f"{self.active_role.title()} active · {ORC_VERSION} · {FOCUS_STATUS}"
        state = load_state(args.state_file)
        record = state.get(self.task_id)
        if not isinstance(record, dict):
            return f"{self.task_id}: unknown · round 1/5 · {ORC_VERSION}"
        return self.status_text(record)

    def update_layout(self) -> None:
        if not self.is_running:
            return
        width = self.size.width
        height = self.size.height - 1
        panes = self.query_one("#panes", Container)
        state = load_state(self.args.state_file)
        record = state.get(self.task_id)
        active_role = (
            self.active_workflow_role(record) if isinstance(record, dict) else None
        )

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
            if role == active_role:
                pane.add_class("active-pane")
            else:
                pane.remove_class("active-pane")
            pane.styles.display = (
                "block"
                if mode != "single" or role == (active_role or "implementer")
                else "none"
            )

        if mode != self.layout_mode:
            self.layout_mode = mode
            self.schedule_resize()
        self.refresh_status()

    def update_status(self, message: str) -> None:
        self.last_status = message
        if getattr(self, "_running", False):
            state = load_state(self.args.state_file)
            record = state.get(self.task_id)
            if isinstance(record, dict) and message == self.status_text(record):
                self.render_status_bar(record)
                return
            # Keep transient PTY errors visible while retaining the composed
            # status widgets for normal workflow updates.
            try:
                widget = self.query_one("#status-message", Static)
            except Exception:
                return
            widget.update(message)

    def poll_state(self) -> None:
        state = load_state(self.args.state_file)
        record = state.get(self.task_id)
        if not isinstance(record, dict):
            return

        self.retire_completed_sessions(record)

        status = record.get("status")
        if status == "completed":
            self.refresh_workflow_ui()
            return
        if status in {"paused", "blocked", "stopped"}:
            self.refresh_workflow_ui()
            return

        if deadline_expired(record):
            set_stop_reason(record, "deadline")
            save_state(self.args.state_file, state)
            self.refresh_workflow_ui()
            return

        if record.get("phase") in {"reviewer", "implementer"}:
            self.launch_role(str(record["phase"]))
        self.refresh_status()

    def poll_children(self) -> None:
        sessions = [
            *list(self.sessions.values()),
            *list(getattr(self, "retired_sessions", [])),
        ]
        for session in sessions:
            if session.exited:
                continue
            try:
                pid, _status = os.waitpid(session.pid, os.WNOHANG)
            except ChildProcessError:
                pid = session.pid
                _status = 0
            if pid == session.pid:
                session.exited = True
                try:
                    if self.event_loop is not None:
                        self.event_loop.remove_reader(session.master_fd)
                except (NotImplementedError, ValueError):
                    pass
                state = load_state(self.args.state_file)
                record = state.get(self.task_id)
                if getattr(session, "retired", False):
                    try:
                        os.close(session.master_fd)
                    except OSError:
                        pass
                    if session in getattr(self, "retired_sessions", []):
                        self.retired_sessions.remove(session)
                    self.refresh_status()
                    continue
                if (
                    isinstance(record, dict)
                    and getattr(session, "backend", "codex") == "claude"
                ):
                    self.drain_session(session)
                    self.handle_claude_exit(session, state, record, _status)
                    continue
                if (
                    isinstance(record, dict)
                    and record.get("status") not in TERMINAL_TASK_STATUSES
                    and child_exit_code(_status) != 0
                ):
                    record["child_failure"] = {
                        "role": session.role,
                        "backend": "codex",
                        "exit_status": _status,
                        "reason": (
                            f"Codex exited with status {child_exit_code(_status)}"
                        ),
                        "time": iso_now(),
                    }
                    set_stop_reason(record, "child_failure")
                    save_state(self.args.state_file, state)
                    self.refresh_workflow_ui()
                    continue
                expected_handoff = (
                    isinstance(record, dict) and record.get("phase") != session.role
                )
                if (
                    session.role == "implementer"
                    and isinstance(record, dict)
                    and record.get("phase") == "reviewer"
                ):
                    session.pane.show_message("Igor idle · waiting for Rufus review")
                elif (
                    session.role == "reviewer"
                    and isinstance(record, dict)
                    and (
                        record.get("phase") in {"implementer", "complete"}
                        or record.get("status") == "paused"
                    )
                ):
                    session.pane.show_message("Rufus idle · review round complete")
                if (
                    isinstance(record, dict)
                    and record.get("status") == "active"
                    and record.get("phase") == session.role
                ):
                    record["child_failure"] = {
                        "role": session.role,
                        "exit_status": _status,
                        "time": iso_now(),
                    }
                    set_stop_reason(record, "child_failure")
                    save_state(self.args.state_file, state)
                    self.refresh_workflow_ui()
                elif session.role == self.active_role and not expected_handoff:
                    self.refresh_status()
                self.refresh_status()

    def on_key(self, event: Any) -> None:
        key = event.key
        if key == "ctrl+q":
            self.exit()
            event.stop()
            return
        special_keys = {
            "tab": b"\x09",
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
        data = special_keys.get(key)
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
        event.stop()

    def on_mouse_down(self, event: MouseDown) -> None:
        event.stop()

    def on_mouse_up(self, event: MouseUp) -> None:
        event.stop()

    def on_mouse_release(self, event: MouseRelease) -> None:
        event.stop()

    async def action_quit(self) -> None:
        self.exit()

    def on_unmount(self) -> None:
        sessions = [
            *self.sessions.values(),
            *getattr(self, "retired_sessions", []),
        ]
        for session in sessions:
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

    backend = selected_backend(args)
    configured_command = (
        claude_command()
        if backend == "claude"
        else backend_command_value(getattr(args, "codex", None) or codex_command())
    )
    backend_version = (
        probe_claude(configured_command) if backend == "claude" else "unknown"
    )
    stored_command: str | list[str] = (
        configured_command[0] if len(configured_command) == 1 else configured_command
    )
    max_rounds = int(getattr(args, "max_rounds", DEFAULT_MAX_ROUNDS))
    deadline_seconds = int(getattr(args, "deadline_minutes", 60) * 60)
    started = utc_now()
    state[args.task_id] = {
        "status": "active",
        "phase": "implementer",
        "round": 1,
        "prompt": args.prompt,
        "target_directory": str(target_directory),
        "implementer_id": None,
        "reviewer_id": None,
        "user_requests": [],
        "last_reviewer_event": None,
        "reviewer_reported_complete": False,
        "handoffs": [],
        "processed_idle_events": [],
        "automatic_rounds": True,
        "max_rounds": max_rounds,
        "deadline_seconds": deadline_seconds,
        "cycle_started_at": started.isoformat(timespec="seconds"),
        "deadline_at": (started + timedelta(seconds=deadline_seconds)).isoformat(
            timespec="seconds"
        ),
        "last_role": None,
        "last_commit": None,
        "role_generations": {"implementer": 0, "reviewer": 0},
        "stop_reason": None,
        "backend": backend,
        "backend_command": stored_command,
        "backend_version": backend_version,
        "claude_session_id": None,
        "claude_final_response": None,
        "claude_sessions": {},
    }
    save_state(args.state_file, state)
    run_app(args, args.task_id)


def resume(args: argparse.Namespace) -> None:
    state = load_state(args.state_file)
    record = state.get(args.task_id)
    if not isinstance(record, dict):
        raise SystemExit(f"unknown task: {args.task_id}")

    stored_target = record.get("target_directory")
    if not isinstance(stored_target, str) or not stored_target:
        raise SystemExit(
            f"task {args.task_id} has no stored target directory; begin a new task"
        )
    target_directory = normalize_target_directory(Path(stored_target))
    # Direct callers from older integrations may still provide a directory on
    # the Namespace. The public parser no longer accepts it; validating it
    # here keeps the internal function safe during that transition.
    supplied_directory = getattr(args, "directory", None)
    if supplied_directory is not None:
        supplied = normalize_target_directory(supplied_directory)
        if supplied != target_directory:
            raise SystemExit(
                f"target directory does not match task {args.task_id}: "
                f"stored {target_directory}, received {supplied}"
            )
    try:
        backend = backend_from_record(record)
    except SystemExit as error:
        raise SystemExit(f"cannot resume task {args.task_id}: {error}") from error
    if not isinstance(args.prompt, str) or not args.prompt.strip():
        raise SystemExit("resume requires a non-empty clarification or request")
    if record.get("status") == "active":
        raise SystemExit(f"task {args.task_id} is already active")
    if record.get("status") == "completed":
        raise SystemExit(f"task {args.task_id} is already complete")
    if record.get("phase") == "complete" or record.get("stop_reason") == "completion":
        raise SystemExit(f"task {args.task_id} is already complete")
    requests = record.get("user_requests")
    if requests is None:
        requests = record.get("user_feedback", [])
    if not isinstance(requests, list):
        raise SystemExit(f"Orc state for {args.task_id} has invalid user_requests")
    automatic = bool(record.get("automatic_rounds"))
    if automatic:
        max_rounds = valid_round_limit(record.get("max_rounds"))
        deadline_seconds = valid_deadline_seconds(record.get("deadline_seconds"))
        if max_rounds is None or deadline_seconds is None:
            raise SystemExit(
                f"task {args.task_id} has invalid automatic limits; "
                "expected 1-5 rounds and 1-1440 minutes"
            )
        deadline_at = parse_timestamp(record.get("deadline_at"))
        if deadline_at is None:
            raise SystemExit(
                f"task {args.task_id} has no valid persisted automatic deadline"
            )
        if deadline_at <= utc_now():
            raise SystemExit(f"task {args.task_id} deadline has expired")
    else:
        max_rounds = valid_round_limit(record.get("max_rounds")) or DEFAULT_MAX_ROUNDS
        deadline_seconds = (
            valid_deadline_seconds(record.get("deadline_seconds"))
            or DEFAULT_DEADLINE_SECONDS
        )

    configured_command = stored_backend_command(record, backend)
    if backend == "claude":
        probe_claude(configured_command)

    child_failure = record.get("child_failure")
    reviewer_rollout_failed = (
        record.get("stop_reason") == "child_failure"
        and isinstance(child_failure, dict)
        and child_failure.get("role") == "reviewer"
    )

    # All validation is complete before changing the loaded record.
    requests = list(requests)
    requests.append(args.prompt)
    record["user_requests"] = requests
    record["last_user_request"] = args.prompt
    record.pop("child_failure", None)
    previous_status = record.get("status")
    record["status"] = "active"
    if reviewer_rollout_failed:
        # A missing Codex rollout cannot be resumed.  Preserve Igor's commit
        # and review round, but force a new Rufus session on the next launch.
        record["reviewer_id"] = None
        record["reviewer_reported_complete"] = False
        record["phase"] = "reviewer"
    else:
        record["phase"] = "implementer"
    if not automatic:
        started = utc_now()
        record["automatic_rounds"] = True
        record["max_rounds"] = max_rounds
        record["deadline_seconds"] = deadline_seconds
        record["cycle_started_at"] = started.isoformat(timespec="seconds")
        record["deadline_at"] = (
            started + timedelta(seconds=deadline_seconds)
        ).isoformat(timespec="seconds")
    record["target_directory"] = str(target_directory)
    record["backend"] = backend
    record["backend_command"] = (
        configured_command[0]
        if len(configured_command) == 1
        else configured_command
    )
    record["round"] = current_round(record)
    record["stop_reason"] = None
    record["clarification_received"] = (
        args.prompt
        if previous_status == "blocked"
        else record.get("clarification_received")
    )
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

    status = handoff_status(payload)
    reason = handoff_reason(payload)
    if status == UNABLE_TO_PROCEED and not reason:
        raise SystemExit("UNABLE_TO_PROCEED handoff requires a concise reason")

    event_key = handoff_event_key(task_id, role, payload)
    processed = record.get("processed_idle_events", [])
    if not isinstance(processed, list):
        processed = []
    if event_key in processed:
        return
    if record.get("status") in {"blocked", "stopped", "completed"}:
        return
    current_phase = record.get("phase")
    if current_phase in {"implementer", "reviewer"} and current_phase != role:
        return
    if record.get("status") == "paused" and role == "reviewer":
        return

    expected_session = record.get(f"{role}_id")
    if (
        isinstance(expected_session, str)
        and expected_session
        and session_id
        and session_id != expected_session
    ):
        return
    expected_round = int(record.get("round", 0))
    generations = record.get("role_generations", {})
    generation_tracking = isinstance(generations, dict) and role in generations
    for key, expected in (("round", expected_round), ("generation", None)):
        value = payload_field(payload, key)
        if value is None and generation_tracking and key == "round":
            value = os.environ.get("ORC_ROUND")
        if value is None and generation_tracking and key == "generation":
            value = os.environ.get("ORC_ROLE_GENERATION")
        if value is None:
            continue
        try:
            actual = int(value)
        except (TypeError, ValueError):
            return
        if key == "generation":
            expected = generations.get(role)
        if expected is not None and actual != int(expected):
            return
    if deadline_expired(record):
        set_stop_reason(record, "deadline")
        save_state(args.state_file, state)
        return

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
        "time": iso_now(),
        "local_time": datetime.now().astimezone().isoformat(timespec="seconds"),
        "task_id": task_id,
        "role": role,
        "round": record.get("round", 0),
        "thread_id": handoff_thread_id,
        "target_directory": str(target_directory),
        "commit": current_commit(target_directory),
        "message": assistant_message_from_payload(payload),
        "status": status,
    }
    generation = payload_field(payload, "generation")
    if generation is None:
        generation = os.environ.get("ORC_ROLE_GENERATION")
    if generation is not None:
        try:
            handoff["generation"] = int(generation)
        except (TypeError, ValueError):
            pass
    handoff.update(handoff_details(payload))
    if status == UNABLE_TO_PROCEED:
        handoff["reason"] = reason
    handoffs = record.setdefault("handoffs", [])
    if not isinstance(handoffs, list):
        handoffs = []
        record["handoffs"] = handoffs
    handoffs.append(handoff)
    record["last_handoff"] = handoff
    record["last_role"] = role
    record["last_commit"] = handoff["commit"]
    processed.append(event_key)
    record["processed_idle_events"] = processed[-20:]

    if status == UNABLE_TO_PROCEED:
        record["blocker_role"] = role
        record["blocker_reason"] = reason
        record["blocked_task"] = task_id
        record["blocked_round"] = record.get("round", 0)
        record["blocked_thread"] = handoff_thread_id
        record["blocked_at"] = handoff["time"]
        record["blocked_commit"] = handoff["commit"]
        record["last_reviewer_event"] = (
            payload if role == "reviewer" else record.get("last_reviewer_event")
        )
        set_stop_reason(record, "clarification")
        save_state(args.state_file, state)
        return

    if role == "implementer":
        if int(record.get("round", 0)) == 0:
            record["round"] = 1
        record["phase"] = "reviewer"
        save_state(args.state_file, state)
        return

    record["last_reviewer_event"] = payload
    message = assistant_message_from_payload(payload) or ""
    record["reviewer_reported_complete"] = status == "COMPLETE" or bool(
        re.search(r"(?im)^\s*TASK COMPLETE\s*$", message)
    )
    if record["reviewer_reported_complete"]:
        set_stop_reason(record, "completion", completed=True)
    else:
        maximum = valid_round_limit(record.get("max_rounds")) or DEFAULT_MAX_ROUNDS
        if current_round(record) >= maximum:
            set_stop_reason(record, "max_rounds")
        else:
            record["round"] = current_round(record) + 1
            record["phase"] = "implementer"
            record["status"] = "active"
            record["stop_reason"] = None
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
