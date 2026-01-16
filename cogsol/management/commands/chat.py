from __future__ import annotations

import json
import os
import shutil
import sys
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, cast

from cogsol.core.api import CogSolAPIError, CogSolClient
from cogsol.core.env import load_dotenv
from cogsol.management.base import BaseCommand

# ═══════════════════════════════════════════════════════════════════════════════
# Terminal Colors & Styling
# ═══════════════════════════════════════════════════════════════════════════════


class Style:
    """ANSI escape codes for terminal styling."""

    # Check if terminal supports colors
    ENABLED = sys.stdout.isatty()

    # Reset
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITALIC = "\033[3m"

    # Colors
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    # Bright colors
    BRIGHT_BLACK = "\033[90m"
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"

    # Background colors
    BG_BLACK = "\033[40m"
    BG_BLUE = "\033[44m"
    BG_CYAN = "\033[46m"
    BG_WHITE = "\033[47m"
    BG_BRIGHT_BLACK = "\033[100m"

    @classmethod
    def apply(cls, text: str, *styles: str) -> str:
        if not cls.ENABLED:
            return text
        style_str = "".join(styles)
        return f"{style_str}{text}{cls.RESET}"


# ═══════════════════════════════════════════════════════════════════════════════
# UI Components
# ═══════════════════════════════════════════════════════════════════════════════


def get_terminal_width() -> int:
    """Get terminal width, with fallback."""
    try:
        return shutil.get_terminal_size().columns
    except Exception:
        return 80


def clear_line() -> None:
    """Clear the current line."""
    if Style.ENABLED:
        print("\033[2K\033[1G", end="", flush=True)


def print_banner(agent_name: str, agent_id: int) -> None:
    """Print a beautiful startup banner."""
    width = min(get_terminal_width(), 70)

    # Gradient-style banner
    banner_art = r"""
 ██████╗ ██████╗  ██████╗ ███████╗ ██████╗ ██╗
██╔════╝██╔═══██╗██╔════╝ ██╔════╝██╔═══██╗██║
██║     ██║   ██║██║  ███╗███████╗██║   ██║██║
██║     ██║   ██║██║   ██║╚════██║██║   ██║██║
╚██████╗╚██████╔╝╚██████╔╝███████║╚██████╔╝███████╗
 ╚═════╝ ╚═════╝  ╚═════╝ ╚══════╝ ╚═════╝ ╚══════╝
    """

    print()
    # Print banner with gradient effect
    lines = banner_art.split("\n")
    max_line_length = max(len(line) for line in lines)
    colors = [
        Style.BRIGHT_CYAN,
        Style.CYAN,
        Style.BRIGHT_BLUE,
        Style.BLUE,
        Style.BRIGHT_MAGENTA,
        Style.MAGENTA,
    ]
    for i, line in enumerate(lines[1:-1]):
        color = colors[i % len(colors)]
        print(Style.apply(line.ljust(max_line_length).center(width), color, Style.BOLD))

    print()

    # Decorative line
    print(Style.apply("━" * width, Style.BRIGHT_BLACK))
    print()

    # Info section with icons
    agent_display = Style.apply(f" {agent_name} ", Style.BOLD, Style.BRIGHT_WHITE, Style.BG_BLUE)
    id_display = Style.apply(f"#{agent_id}", Style.DIM, Style.BRIGHT_BLACK)

    print(f"  🤖  Agent: {agent_display} {id_display}")
    print(f"  📅  {Style.apply(datetime.now().strftime('%B %d, %Y • %H:%M'), Style.DIM)}")
    print()

    # Commands help
    print(Style.apply("  ╭─────────────────────────────────────────╮", Style.BRIGHT_BLACK))
    print(
        Style.apply("  │", Style.BRIGHT_BLACK)
        + Style.apply("  Commands:", Style.BOLD, Style.WHITE)
        + Style.apply("                              │", Style.BRIGHT_BLACK)
    )
    print(
        Style.apply("  │", Style.BRIGHT_BLACK)
        + Style.apply("    /exit", Style.CYAN)
        + Style.apply(" or ", Style.DIM)
        + Style.apply("Ctrl+C", Style.CYAN)
        + Style.apply("  →  Quit chat", Style.DIM)
        + Style.apply("        │", Style.BRIGHT_BLACK)
    )
    print(
        Style.apply("  │", Style.BRIGHT_BLACK)
        + Style.apply("    /new", Style.CYAN)
        + Style.apply("             →  Start a new chat", Style.DIM)
        + Style.apply(" │", Style.BRIGHT_BLACK)
    )
    print(Style.apply("  ╰─────────────────────────────────────────╯", Style.BRIGHT_BLACK))
    print()
    print(Style.apply("━" * width, Style.BRIGHT_BLACK))
    print()


def print_thinking_animation() -> None:
    """Print a thinking indicator."""
    print(
        Style.apply("  ◌ ", Style.BRIGHT_BLUE)
        + Style.apply("Thinking...", Style.DIM, Style.ITALIC),
        end="",
        flush=True,
    )


def clear_thinking() -> None:
    """Clear the thinking animation."""
    clear_line()


def format_timestamp() -> str:
    """Get formatted current time."""
    return datetime.now().strftime("%H:%M")


def wrap_text(text: str, width: int, indent: str = "") -> list[str]:
    """Wrap text to specified width with indent."""
    lines = []
    for paragraph in text.split("\n"):
        if paragraph.strip():
            wrapped = textwrap.wrap(
                paragraph, width=width - len(indent), break_long_words=False, break_on_hyphens=False
            )
            lines.extend(wrapped if wrapped else [""])
        else:
            lines.append("")
    return lines


def print_user_message(content: str) -> None:
    """Print a user message bubble (right-aligned style)."""
    width = min(get_terminal_width(), 80)
    max_bubble_width = int(width * 0.7)
    timestamp = format_timestamp()

    lines = wrap_text(content, max_bubble_width - 4)
    bubble_width = max(len(line) for line in lines) + 4 if lines else 20
    bubble_width = min(bubble_width, max_bubble_width)

    padding = width - bubble_width - 2

    # User message - right side, cyan theme
    print()

    # Top of bubble
    top = "╭" + "─" * (bubble_width - 2) + "╮"
    print(" " * padding + Style.apply(top, Style.CYAN))

    # Content
    for line in lines:
        padded_line = line.ljust(bubble_width - 4)
        print(
            " " * padding
            + Style.apply("│ ", Style.CYAN)
            + Style.apply(padded_line, Style.WHITE)
            + Style.apply(" │", Style.CYAN)
        )

    # Bottom of bubble
    bottom = "╰" + "─" * (bubble_width - 2) + "╯"
    print(" " * padding + Style.apply(bottom, Style.CYAN))

    # Timestamp and sender
    meta = f"You • {timestamp} "
    print(" " * (width - len(meta) - 1) + Style.apply(meta, Style.DIM))


def print_ai_message(content: str) -> None:
    """Print an AI message bubble (left-aligned style)."""
    width = min(get_terminal_width(), 80)
    max_bubble_width = int(width * 0.75)
    timestamp = format_timestamp()

    lines = wrap_text(content, max_bubble_width - 4)
    bubble_width = max(len(line) for line in lines) + 4 if lines else 20
    bubble_width = min(bubble_width, max_bubble_width)

    print()

    # AI avatar
    print(Style.apply("  🤖", Style.BRIGHT_GREEN))

    # Top of bubble
    top = "  ╭" + "─" * (bubble_width - 2) + "╮"
    print(Style.apply(top, Style.GREEN))

    # Content
    for line in lines:
        padded_line = line.ljust(bubble_width - 4)
        print(
            Style.apply("  │ ", Style.GREEN)
            + Style.apply(padded_line, Style.BRIGHT_WHITE)
            + Style.apply(" │", Style.GREEN)
        )

    # Bottom of bubble
    bottom = "  ╰" + "─" * (bubble_width - 2) + "╯"
    print(Style.apply(bottom, Style.GREEN))

    # Timestamp
    print(Style.apply(f"   Assistant • {timestamp}", Style.DIM))


def print_error(message: str) -> None:
    """Print an error message."""
    print()
    print(Style.apply("  ⚠️  ", Style.BRIGHT_YELLOW) + Style.apply(message, Style.YELLOW))
    print()


def print_system_message(message: str) -> None:
    """Print a system message."""
    width = min(get_terminal_width(), 70)
    print()
    print(Style.apply(f"  ┄┄┄ {message} ┄┄┄".center(width), Style.DIM))
    print()


def print_goodbye() -> None:
    """Print a goodbye message."""
    print()
    print(Style.apply("  ╭───────────────────────────────────────╮", Style.BRIGHT_MAGENTA))
    print(
        Style.apply("  │", Style.BRIGHT_MAGENTA)
        + Style.apply("     👋  Thanks for chatting!          ", Style.WHITE)
        + Style.apply("│", Style.BRIGHT_MAGENTA)
    )
    print(
        Style.apply("  │", Style.BRIGHT_MAGENTA)
        + Style.apply("         See you next time!            ", Style.DIM)
        + Style.apply("│", Style.BRIGHT_MAGENTA)
    )
    print(Style.apply("  ╰───────────────────────────────────────╯", Style.BRIGHT_MAGENTA))
    print()


def get_input_prompt() -> str:
    """Get the styled input prompt."""
    return Style.apply("  ╰─▶ ", Style.CYAN, Style.BOLD) if Style.ENABLED else "  > "


class Command(BaseCommand):
    help = "Open an interactive console to chat with a CogSol assistant."

    def add_arguments(self, parser):
        parser.add_argument(
            "--agent", required=True, help="Agent name (as defined in code) or remote ID."
        )
        parser.add_argument("app", nargs="?", default="agents", help="App name. Default: agents.")

    def handle(self, project_path: Path | None, **options: Any) -> int:
        assert project_path is not None, "project_path is required"
        agent = str(options.get("agent") or "")
        app = str(options.get("app") or "agents")
        load_dotenv(project_path / ".env")

        api_base = os.environ.get("COGSOL_API_BASE")
        api_token = os.environ.get("COGSOL_API_TOKEN")
        if not api_base:
            print_error("COGSOL_API_BASE is required in .env to chat with CogSol.")
            return 1

        remote_ids = self._load_remote_ids(project_path, app)
        assistant_id = self._resolve_agent_id(agent, remote_ids)
        if assistant_id is None:
            print_error(f"Could not resolve agent '{agent}'. Run migrate first.")
            return 1

        client = CogSolClient(api_base, token=api_token)
        initial_message = self._assistant_initial_message(client, assistant_id)

        # Start a new chat and show banner
        if Style.ENABLED:
            print("\033[2J\033[H", end="")  # Start a new chat

        print_banner(agent, assistant_id)
        if initial_message:
            print_ai_message(initial_message)

        chat_id: Optional[int] = None
        history_printed = 0

        while True:
            try:
                # Show input area
                print(Style.apply("  ╭─ Message", Style.CYAN, Style.DIM))
                user_msg = input(get_input_prompt()).strip()
            except (EOFError, KeyboardInterrupt):
                print_goodbye()
                return 0

            if not user_msg:
                # Clear the empty input lines
                if Style.ENABLED:
                    print("\033[2A\033[J", end="")  # Move up 2 lines and clear
                continue

            if user_msg.lower() in {"/exit", "exit", "quit", ":q"}:
                print_goodbye()
                return 0

            if user_msg.lower() in {"/new", "new", "/restart", "/reset"}:
                chat_id = None
                history_printed = 0
                print_system_message(
                    "Started a new chat. Your next message will open a fresh session."
                )
                if initial_message:
                    print_ai_message(initial_message)
                continue

            # Display user's message
            print_user_message(user_msg)

            # Show thinking animation
            print_thinking_animation()

            try:
                if chat_id is None:
                    chat = client.create_chat(assistant_id, user_msg)
                    chat_id = self._chat_id(chat)
                else:
                    chat = client.send_message(chat_id, user_msg)

                messages = self._extract_messages(chat)

                # If API does not return messages, fetch explicitly
                if not messages and chat_id:
                    chat = client.get_chat(chat_id)
                    messages = self._extract_messages(chat)

                # Clear thinking animation
                clear_thinking()

                # Print only new AI messages (skip user messages we already printed)
                self._print_new_ai_messages(
                    messages,
                    since=history_printed,
                    initial_message=initial_message,
                )
                history_printed = len(messages)

            except CogSolAPIError as exc:
                clear_thinking()
                print_error(f"API Error: {exc}")
            except Exception as exc:  # pragma: no cover - safety net
                clear_thinking()
                print_error(f"Error: {exc}")

        return 0

    # Helpers -----------------------------------------------------------------
    def _load_remote_ids(self, project_path: Path, app: str) -> dict[str, Any]:
        state_path = project_path / app / "migrations" / ".state.json"
        if not state_path.exists():
            return {}
        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("remote"), dict):
                return cast(dict[str, Any], data["remote"])
            if isinstance(data, dict):
                return cast(dict[str, Any], data.get("remote", {}))
            return {}
        except json.JSONDecodeError:
            return {}

    def _resolve_agent_id(self, agent: str, remote_ids: dict[str, Any]) -> Optional[int]:
        # direct numeric id
        try:
            return int(agent)
        except (TypeError, ValueError):
            pass
        value = remote_ids.get("agents", {}).get(agent)
        return value if isinstance(value, int) else None

    def _assistant_initial_message(self, client: CogSolClient, assistant_id: int) -> str:
        try:
            assistant = client.get_assistant(assistant_id)
        except CogSolAPIError:
            return ""
        if isinstance(assistant, dict):
            value = assistant.get("initial_message")
            if isinstance(value, str):
                return value.strip()
        return ""

    def _chat_id(self, chat_obj: Any) -> Optional[int]:
        if isinstance(chat_obj, dict):
            value = chat_obj.get("id")
            if isinstance(value, int):
                return value
        return None

    def _extract_messages(self, chat_obj: Any) -> list[dict[str, Any]]:
        if not isinstance(chat_obj, dict):
            return []
        msgs = chat_obj.get("messages") or []
        if isinstance(msgs, list):
            return msgs
        return []

    def _print_new_ai_messages(
        self,
        messages: list[dict[str, Any]],
        since: int,
        initial_message: str = "",
    ) -> None:
        """Print only new AI messages (user messages are printed immediately on input)."""
        if not messages:
            print_error("No response received")
            return

        new_msgs = messages[since:]
        if initial_message and since == 0:
            for idx, msg in enumerate(new_msgs):
                if msg.get("role", "assistant") != "user" and msg.get("content") == initial_message:
                    new_msgs = new_msgs[idx + 1 :]
                    break
        for msg in new_msgs:
            role = msg.get("role", "assistant")
            content = msg.get("content") or ""

            # Only print AI/assistant messages - user messages are already shown
            if role != "user" and content.strip():
                print_ai_message(content)
