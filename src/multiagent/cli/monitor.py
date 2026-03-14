# pyright: reportUnknownMemberType=false, reportMissingTypeArgument=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportCallIssue=false
# ruff: noqa: D102, D107
"""Platform monitor TUI — live dashboard for the multiagent system."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite
import typer
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widget import Widget
from textual.widgets import (
    Footer,
    Header,
    Input,
    Label,
    OptionList,
    Static,
)
from textual.widgets.option_list import Option

from multiagent.config import load_settings
from multiagent.config.agents import load_agents_config
from multiagent.transport.base import Message

_POLL_SECONDS = 2.0


class AgentsPanel(Widget):
    """Shows agent names with active/idle status."""

    DEFAULT_CSS = """
    AgentsPanel {
        border: solid $secondary;
        height: auto;
        max-height: 50%;
        padding: 0 1;
    }
    AgentsPanel .agent-title {
        text-style: bold;
        margin-bottom: 1;
    }
    AgentsPanel .agent-stats {
        color: $text-muted;
        margin-top: 1;
    }
    """

    def __init__(self, agent_names: list[str], poll_interval: float) -> None:
        super().__init__()
        self._agent_names = agent_names
        self._poll_interval = poll_interval
        self._status: dict[str, bool] = dict.fromkeys(agent_names, False)
        self._thread_count = 0
        self.border_title = "Agents"

    def compose(self) -> ComposeResult:
        yield Static("", id="agent-list")
        yield Static("", id="agent-stats", classes="agent-stats")

    def update_status(
        self, status: dict[str, bool], thread_count: int
    ) -> None:
        """Refresh agent statuses and thread count."""
        self._status = status
        self._thread_count = thread_count
        lines: list[str] = []
        for name in self._agent_names:
            active = self._status.get(name, False)
            if active:
                line = f"[green]●[/] [bold]{name:<12}[/] [bold]active[/]"
            else:
                line = f"[dim]○[/] {name:<12} [dim]idle[/]"
            lines.append(line)
        rendered = "\n".join(lines)
        try:
            self.query_one("#agent-list", Static).update(rendered)
        except Exception:
            pass
        stats = (
            f"\n[dim]Poll: {self._poll_interval}s\n"
            f"Threads: {self._thread_count}[/]"
        )
        try:
            self.query_one("#agent-stats", Static).update(stats)
        except Exception:
            pass


class ThreadsPanel(Widget):
    """Selectable list of threads with cost and message count."""

    DEFAULT_CSS = """
    ThreadsPanel {
        border: solid $secondary;
        height: 1fr;
        padding: 0;
    }
    ThreadsPanel OptionList {
        height: 100%;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._threads: list[dict[str, Any]] = []
        self.border_title = "Threads"

    def compose(self) -> ComposeResult:
        yield OptionList(id="thread-list")

    @property
    def selected_thread_id(self) -> str | None:
        """Return the currently highlighted thread_id, or None."""
        try:
            ol = self.query_one("#thread-list", OptionList)
            idx = ol.highlighted
            if idx is not None and idx < len(self._threads):
                return str(self._threads[idx]["thread_id"])
        except Exception:
            pass
        return None

    def update_threads(self, threads: list[dict[str, Any]]) -> None:
        """Refresh the thread list. Preserves selection if possible."""
        prev_id = self.selected_thread_id
        self._threads = threads
        try:
            ol = self.query_one("#thread-list", OptionList)
        except Exception:
            return
        ol.clear_options()
        restore_idx = 0
        for i, t in enumerate(threads):
            tid_short = str(t["thread_id"])[:8]
            cost = t.get("cost")
            cost_str = f"${cost:.3f}" if cost is not None else "—"
            count = t.get("msg_count", 0)
            label = f"  {tid_short}  {cost_str:>8}  {count:>3}"
            ol.add_option(Option(label))
            if prev_id and str(t["thread_id"]) == prev_id:
                restore_idx = i
        if threads:
            ol.highlighted = restore_idx

    def select_thread(self, thread_id: str) -> None:
        """Programmatically select a thread by ID."""
        for i, t in enumerate(self._threads):
            if str(t["thread_id"]) == thread_id:
                try:
                    ol = self.query_one("#thread-list", OptionList)
                    ol.highlighted = i
                except Exception:
                    pass
                break


class ThreadPanel(Widget, can_focus=True):
    """Displays the message chain for the selected thread.

    Focus this panel (click or tab) then use j/k to move between
    messages and Enter to expand/collapse.
    """

    DEFAULT_CSS = """
    ThreadPanel {
        border: solid $secondary;
        height: 100%;
        padding: 0 1;
    }
    ThreadPanel:focus {
        border: solid $accent;
    }
    ThreadPanel #thread-scroll {
        height: 100%;
    }
    """

    BINDINGS = [  # noqa: RUF012  # type: ignore[assignment]
        Binding("j", "cursor_down", "Msg ↓", show=False),
        Binding("k", "cursor_up", "Msg ↑", show=False),
        Binding("down", "cursor_down", "Msg ↓", show=False),
        Binding("up", "cursor_up", "Msg ↑", show=False),
        Binding("enter", "toggle_selected", "Toggle", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._auto_scroll = True
        self._last_count = 0
        self._messages: list[dict[str, Any]] = []
        self._expanded: set[int] = set()
        self._cursor: int | None = None
        self.border_title = "Thread"

    def compose(self) -> ComposeResult:
        yield VerticalScroll(
            Static("Select a thread", id="thread-content"),
            id="thread-scroll",
        )

    @staticmethod
    def _esc(text: str) -> str:
        """Escape markup special characters in user content."""
        return text.replace("[", r"\[")

    def _render_thread(self) -> None:
        """Rebuild the full thread display."""
        if not self._messages:
            try:
                self.query_one("#thread-content", Static).update(
                    "No messages"
                )
            except Exception:
                pass
            return

        lines: list[str] = []
        for i, m in enumerate(self._messages):
            from_a = str(m.get("from_agent", "?"))
            to_a = str(m.get("to_agent", "?"))
            body = str(m.get("body", ""))

            ts_raw = m.get("created_at", "")
            ts_str = ""
            if ts_raw:
                try:
                    dt = datetime.fromisoformat(str(ts_raw))
                    ts_str = dt.strftime("%H:%M:%S")
                except (ValueError, TypeError):
                    ts_str = str(ts_raw)[:8]

            unprocessed = m.get("processed_at") is None
            dot = " [yellow]●[/]" if unprocessed else ""

            # Cursor marker — always visible so user knows which message is selected
            cursor = "[bold yellow]▶[/] " if i == self._cursor else "  "

            header = (
                f"{cursor}"
                f"[bold]{self._esc(from_a):<10}[/]"
                f" → "
                f"{self._esc(to_a):<10}"
            )

            is_long = len(body) > 80 or "\n" in body

            if i in self._expanded:
                line = (
                    f"{header}  [dim]{ts_str}[/]{dot}"
                    f" [dim]▾[/]\n  {self._esc(body)}"
                )
            else:
                truncated = body.replace("\n", " ")
                if len(truncated) > 80:
                    truncated = truncated[:77] + "..."
                indicator = " [dim]▸[/]" if is_long else ""
                line = (
                    f"{header} {self._esc(truncated)}"
                    f"  [dim]{ts_str}[/]{dot}{indicator}"
                )
            lines.append(line)

        rendered = "\n".join(lines)
        try:
            self.query_one("#thread-content", Static).update(rendered)
        except Exception:
            pass

    def update_messages(
        self, messages: list[dict[str, Any]], thread_id: str = ""
    ) -> None:
        """Update the message list and re-render."""
        new_count = len(messages)
        self._messages = messages
        if new_count > 0 and self._cursor is None:
            self._cursor = 0
        elif self._cursor is not None and self._cursor >= new_count:
            self._cursor = new_count - 1 if new_count else None
        self._render_thread()

        if new_count > self._last_count and self._auto_scroll:
            try:
                scroll = self.query_one("#thread-scroll", VerticalScroll)
                scroll.scroll_end(animate=False)
            except Exception:
                pass
        self._last_count = new_count

    def action_cursor_down(self) -> None:
        """Move cursor to the next message."""
        if not self._messages:
            return
        if self._cursor is None:
            self._cursor = 0
        elif self._cursor < len(self._messages) - 1:
            self._cursor += 1
        self._render_thread()

    def action_cursor_up(self) -> None:
        """Move cursor to the previous message."""
        if not self._messages:
            return
        if self._cursor is None:
            self._cursor = len(self._messages) - 1
        elif self._cursor > 0:
            self._cursor -= 1
        self._render_thread()

    def action_toggle_selected(self) -> None:
        """Toggle expand/collapse on the cursor message."""
        if self._cursor is not None:
            self.toggle_message(self._cursor)

    def toggle_message(self, index: int) -> None:
        """Expand or collapse a message by index."""
        if index in self._expanded:
            self._expanded.discard(index)
        else:
            self._expanded.add(index)
        self._render_thread()

    def expand_all(self) -> None:
        """Expand all messages."""
        self._expanded = set(range(len(self._messages)))
        self._render_thread()

    def collapse_all(self) -> None:
        """Collapse all messages."""
        self._expanded.clear()
        self._render_thread()


class SendPanel(Widget):
    """Inline message send form."""

    DEFAULT_CSS = """
    SendPanel {
        border: solid $secondary;
        padding: 0 1;
    }
    SendPanel .send-row {
        layout: horizontal;
        height: auto;
    }
    SendPanel Label {
        width: 9;
        padding: 0 1 0 0;
    }
    SendPanel Input {
        width: 1fr;
    }
    SendPanel #send-body {
        margin-top: 1;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self.border_title = "Send"

    def compose(self) -> ComposeResult:
        with Horizontal(classes="send-row"):
            yield Label("To:")
            yield Input(placeholder="agent name", id="send-to")
        with Horizontal(classes="send-row"):
            yield Label("Thread:")
            yield Input(placeholder="thread UUID", id="send-thread")
        yield Input(placeholder="Type message and press Enter", id="send-body")

    def prefill(self, to_agent: str, thread_id: str) -> None:
        """Pre-fill the To and Thread fields."""
        try:
            self.query_one("#send-to", Input).value = to_agent
            self.query_one("#send-thread", Input).value = thread_id
        except Exception:
            pass

    @property
    def to_agent(self) -> str:
        try:
            return self.query_one("#send-to", Input).value.strip()
        except Exception:
            return ""

    @property
    def thread_id(self) -> str:
        try:
            return self.query_one("#send-thread", Input).value.strip()
        except Exception:
            return ""

    @property
    def body(self) -> str:
        try:
            return self.query_one("#send-body", Input).value.strip()
        except Exception:
            return ""

    def clear_body(self) -> None:
        try:
            self.query_one("#send-body", Input).value = ""
        except Exception:
            pass


class MonitorApp(App[None]):
    """Live platform monitor for the multiagent system."""

    TITLE = "multiagent monitor"

    CSS = """
    #main-layout {
        layout: horizontal;
        height: 1fr;
    }
    #left-col {
        width: 34;
        height: 100%;
    }
    #right-col {
        width: 1fr;
        height: 100%;
    }
    ThreadPanel {
        height: 2fr;
    }
    SendPanel {
        height: 1fr;
        min-height: 7;
    }
    """

    BINDINGS = [  # noqa: RUF012  # type: ignore[assignment]
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("e", "expand_all", "Expand all"),
        Binding("c", "collapse_all", "Collapse all"),
        Binding("f", "focus_thread", "Messages"),
        Binding("tab", "focus_next", "Next field", show=False),
    ]

    def __init__(
        self,
        db_path: Path,
        cost_db_path: Path,
        agent_names: list[str],
        poll_interval: float,
        experiment: str = "",
        initial_thread: str = "",
    ) -> None:
        super().__init__()
        self._db_path = db_path
        self._cost_db_path = cost_db_path
        self._agent_names = agent_names
        self._poll_interval = poll_interval
        self._experiment = experiment
        self._initial_thread = initial_thread
        self._agents_conn: aiosqlite.Connection | None = None
        self._cost_conn: aiosqlite.Connection | None = None
        self._transport: Any = None
        self._refreshing = False

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-layout"):
            with Vertical(id="left-col"):
                yield AgentsPanel(self._agent_names, self._poll_interval)
                yield ThreadsPanel()
            with Vertical(id="right-col"):
                yield ThreadPanel()
                yield SendPanel()
        yield Footer()

    async def on_mount(self) -> None:
        """Open database connections and start polling."""
        # Transport for sending messages
        from multiagent.transport.sqlite import SQLiteTransport

        settings = load_settings()
        self._transport = SQLiteTransport(settings)

        # Read-only connections for display
        self._agents_conn = await aiosqlite.connect(str(self._db_path))
        self._agents_conn.row_factory = aiosqlite.Row

        if self._cost_db_path.exists():
            try:
                self._cost_conn = await aiosqlite.connect(
                    str(self._cost_db_path)
                )
                self._cost_conn.row_factory = aiosqlite.Row
            except Exception:
                self._cost_conn = None
        else:
            self._cost_conn = None

        if self._experiment:
            self.sub_title = f"experiment: {self._experiment}"

        # Initial refresh then start polling
        await self._refresh_all()
        self.set_interval(_POLL_SECONDS, self._refresh_all)

        # Select initial thread if provided
        if self._initial_thread:
            self.query_one(ThreadsPanel).select_thread(self._initial_thread)
            await self._load_selected_thread()

    async def on_unmount(self) -> None:
        """Clean up database connections."""
        if self._agents_conn:
            await self._agents_conn.close()
        if self._cost_conn:
            await self._cost_conn.close()
        if self._transport:
            await self._transport.close()

    async def _refresh_all(self) -> None:
        """Poll all panels."""
        self._refreshing = True
        try:
            await self._refresh_agents()
            await self._refresh_threads()
            await self._load_selected_thread()
            await self._refresh_header_cost()
        except Exception:
            pass
        finally:
            self._refreshing = False

    async def _refresh_agents(self) -> None:
        """Query inbox counts and update agent panel."""
        if not self._agents_conn:
            return
        status: dict[str, bool] = {}
        for name in self._agent_names:
            cursor = await self._agents_conn.execute(
                "SELECT COUNT(*) as cnt FROM messages "
                "WHERE to_agent = ? AND processed_at IS NULL",
                (name,),
            )
            row = await cursor.fetchone()
            status[name] = bool(row and row["cnt"] > 0)

        # Thread count
        cursor = await self._agents_conn.execute(
            "SELECT COUNT(DISTINCT thread_id) as cnt FROM messages"
        )
        row = await cursor.fetchone()
        thread_count = int(row["cnt"]) if row else 0

        self.query_one(AgentsPanel).update_status(status, thread_count)

    async def _refresh_threads(self) -> None:
        """Fetch thread list with costs."""
        if not self._agents_conn:
            return

        # Get thread summaries
        cursor = await self._agents_conn.execute(
            "SELECT thread_id, COUNT(*) as msg_count, "
            "MAX(created_at) as last_activity "
            "FROM messages GROUP BY thread_id "
            "ORDER BY last_activity DESC"
        )
        rows = await cursor.fetchall()

        # Get cost per thread
        cost_map: dict[str, float] = {}
        if self._cost_conn:
            try:
                cost_cursor = await self._cost_conn.execute(
                    "SELECT thread_id, SUM(cost_usd) as total_cost "
                    "FROM cost_ledger GROUP BY thread_id"
                )
                cost_rows = await cost_cursor.fetchall()
                cost_map = {
                    str(r["thread_id"]): float(r["total_cost"])
                    for r in cost_rows
                }
            except Exception:
                pass

        # Experiment filter
        experiment_threads: set[str] | None = None
        if self._experiment and self._cost_conn:
            try:
                exp_cursor = await self._cost_conn.execute(
                    "SELECT DISTINCT thread_id FROM cost_ledger "
                    "WHERE experiment = ?",
                    (self._experiment,),
                )
                exp_rows = await exp_cursor.fetchall()
                experiment_threads = {str(r["thread_id"]) for r in exp_rows}
            except Exception:
                pass

        threads: list[dict[str, Any]] = []
        for r in rows:
            tid = str(r["thread_id"])
            if experiment_threads is not None and tid not in experiment_threads:
                continue
            threads.append({
                "thread_id": tid,
                "msg_count": int(r["msg_count"]),
                "last_activity": r["last_activity"],
                "cost": cost_map.get(tid),
            })

        self.query_one(ThreadsPanel).update_threads(threads)

    async def _load_selected_thread(self) -> None:
        """Load messages for the selected thread."""
        if not self._agents_conn:
            return
        tid = self.query_one(ThreadsPanel).selected_thread_id
        if not tid:
            return

        cursor = await self._agents_conn.execute(
            "SELECT from_agent, to_agent, body, created_at, processed_at "
            "FROM messages WHERE thread_id = ? ORDER BY created_at ASC",
            (tid,),
        )
        rows = await cursor.fetchall()
        messages = [dict(r) for r in rows]

        self.query_one(ThreadPanel).update_messages(messages, tid)
        self.query_one(ThreadPanel).border_title = f"Thread {tid[:8]}"

    async def on_option_list_option_highlighted(
        self, event: OptionList.OptionHighlighted
    ) -> None:
        """When a thread is selected, load its messages and prefill send."""
        if self._refreshing:
            return
        await self._load_selected_thread()
        await self._prefill_send_panel()

    async def _prefill_send_panel(self) -> None:
        """Pre-fill the send panel from the selected thread."""
        if not self._agents_conn:
            return
        tid = self.query_one(ThreadsPanel).selected_thread_id
        if not tid:
            return
        cursor = await self._agents_conn.execute(
            "SELECT from_agent, to_agent FROM messages "
            "WHERE thread_id = ? ORDER BY created_at DESC",
            (tid,),
        )
        rows = list(await cursor.fetchall())
        reply_to = ""
        for r in rows:
            if str(r["to_agent"]) == "human":
                reply_to = str(r["from_agent"])
                break
        if not reply_to and rows:
            reply_to = str(rows[0]["from_agent"])
        self.query_one(SendPanel).prefill(reply_to, tid)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter in the send body input."""
        if event.input.id != "send-body":
            return
        send = self.query_one(SendPanel)
        to_agent = send.to_agent
        body = send.body
        thread_id = send.thread_id

        if not to_agent or not body:
            return

        msg = Message(
            from_agent="human",
            to_agent=to_agent,
            body=body,
        )
        if thread_id:
            msg.thread_id = thread_id

        if self._transport:
            await self._transport.send(msg)
            send.clear_body()
            # Release focus so polling resumes normally
            self.set_focus(None)
            await self._refresh_all()

    async def action_refresh(self) -> None:
        """Manual refresh."""
        await self._refresh_all()

    def action_expand_all(self) -> None:
        """Expand all messages in the thread panel."""
        self.query_one(ThreadPanel).expand_all()

    def action_collapse_all(self) -> None:
        """Collapse all messages in the thread panel."""
        self.query_one(ThreadPanel).collapse_all()

    def action_focus_thread(self) -> None:
        """Focus the thread panel for message navigation."""
        self.query_one(ThreadPanel).focus()

    async def _refresh_header_cost(self) -> None:
        """Update the header subtitle with total cost."""
        if not self._cost_conn:
            return
        try:
            if self._experiment:
                cursor = await self._cost_conn.execute(
                    "SELECT SUM(cost_usd) as total FROM cost_ledger "
                    "WHERE experiment = ?",
                    (self._experiment,),
                )
            else:
                cursor = await self._cost_conn.execute(
                    "SELECT SUM(cost_usd) as total FROM cost_ledger"
                )
            row = await cursor.fetchone()
            total = float(row["total"]) if row and row["total"] else 0.0
            cost_str = f"${total:.4f}"
            if self._experiment:
                self.sub_title = (
                    f"experiment: {self._experiment}  —  {cost_str}"
                )
            else:
                self.sub_title = cost_str
        except Exception:
            pass


def monitor_command(
    experiment: str = typer.Option(
        "",
        "--experiment",
        "-e",
        help="Filter threads by experiment label.",
    ),
    thread_id: str = typer.Option(
        "",
        "--thread-id",
        "-t",
        help="Pre-select a thread on launch.",
    ),
) -> None:
    """Launch the platform monitor TUI.

    Provides a live dashboard showing agent status, message threads,
    cost tracking, and an inline send panel. Requires SQLite transport.
    """
    settings = load_settings()

    if settings.transport_backend != "sqlite":
        print(
            f"Error: monitor requires SQLite transport, "
            f"got '{settings.transport_backend}'",
            file=sys.stderr,
        )
        raise SystemExit(1)

    db_path = settings.sqlite_db_path
    if str(db_path) != ":memory:" and not Path(db_path).exists():
        print(
            f"Error: agents database not found: {db_path}",
            file=sys.stderr,
        )
        raise SystemExit(1)

    if experiment:
        settings.experiment = experiment

    agents_config = load_agents_config(settings.agents_config_path)
    agent_names = list(agents_config.agents.keys())

    app = MonitorApp(
        db_path=Path(db_path),
        cost_db_path=settings.cost_db_path,
        agent_names=agent_names,
        poll_interval=settings.sqlite_poll_interval_seconds,
        experiment=experiment,
        initial_thread=thread_id,
    )
    app.run()
