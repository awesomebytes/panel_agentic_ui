"""Chat session management with UUID-based persistence and Panel UI."""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Awaitable, Callable, Literal

import panel as pn

log = logging.getLogger(__name__)


def _truncate_title(text: str, max_words: int = 5, max_chars: int = 40) -> str:
    """First few words of text for use as chat title."""
    words = text.strip().split()[:max_words]
    s = " ".join(words)
    return s[:max_chars] + ("..." if len(s) > max_chars else "")


class ChatSession:
    """Single chat session with UUID-based ID and JSON persistence."""

    def __init__(self, *, session_id: str | None = None, title: str = "New Chat") -> None:
        self._session_id = str(uuid.uuid4()) if session_id is None else session_id
        self._title = title
        self._history: list[dict] = []
        # Wired by main.py to the LLM generator pipeline
        self.on_generate: Callable[[str], Awaitable[bool]] | None = None

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def title(self) -> str:
        return self._title

    @property
    def history(self) -> list[dict]:
        return self._history.copy()

    def add_message(self, role: Literal["user", "assistant"], content: str) -> None:
        msg = {
            "role": role,
            "content": content,
            "timestamp": time.time(),
        }
        self._history.append(msg)
        if role == "user" and self._title == "New Chat":
            t = _truncate_title(content)
            self._title = t if t else self._title

    def save(self, chats_dir: Path) -> None:
        chats_dir = Path(chats_dir)
        chats_dir.mkdir(parents=True, exist_ok=True)
        path = chats_dir / f"{self._session_id}.json"
        data = {
            "session_id": self._session_id,
            "title": self._title,
            "history": self._history,
        }
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.rename(path)

    @classmethod
    def load(cls, path: Path) -> ChatSession:
        path = Path(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        session = cls(
            session_id=data["session_id"],
            title=data.get("title", "New Chat"),
        )
        session._history = data.get("history", [])
        return session

    def get_panel(
        self,
        chats_dir: Path,
        *,
        on_send: Callable[[str], None] | None = None,
    ) -> pn.viewable.Viewable:
        """Build Panel chat UI with history, input, and send button."""
        from datetime import datetime

        from panel.chat import ChatInterface, ChatMessage

        # Build initial messages from history
        objects: list = []
        for m in self._history:
            ts = m.get("timestamp")
            dt = datetime.fromtimestamp(ts) if isinstance(ts, (int, float)) else None
            objects.append(
                ChatMessage(
                    m["content"],
                    user=m["role"],
                    timestamp=dt,
                )
            )

        async def callback(
            contents: str, user: str, instance: pn.chat.ChatInterface
        ) -> str | None:
            if not contents or not contents.strip():
                return None
            text = contents.strip()
            self.add_message("user", text)
            self.save(chats_dir)
            if on_send:
                on_send(text)
            if self.on_generate:
                await self.on_generate(text)
                # generate_and_load already appended the assistant message to history
                for msg in reversed(self._history):
                    if msg["role"] == "assistant":
                        self.save(chats_dir)
                        return msg["content"]
                return None
            # Fallback echo when no generator is wired
            reply = text
            self.add_message("assistant", reply)
            self.save(chats_dir)
            return reply

        chat = ChatInterface(
            callback=callback,
            objects=objects,
            user="user",
            callback_user="assistant",
            show_rerun=False,
            show_undo=False,
            show_clear=False,
            placeholder_text="Type a message...",
        )

        wrapper = pn.Column(
            chat,
            sizing_mode="stretch_both",
            styles={
                "background": "#ffffff",
                "color": "#333333",
                "font-family": "system-ui, -apple-system, sans-serif",
                "border": "1px solid #e0e0e0",
                "border-radius": "4px",
            },
        )
        return wrapper


class ChatManager:
    """Manages multiple ChatSession instances with pn.Tabs UI."""

    def __init__(self, chats_dir: Path) -> None:
        self._chats_dir = Path(chats_dir)
        self._chats_dir.mkdir(parents=True, exist_ok=True)
        self._sessions: list[ChatSession] = []
        self._load_sessions()
        self.on_user_message: Callable[[ChatSession, str], None] | None = None

    def _load_sessions(self) -> None:
        self._sessions = []
        for path in sorted(self._chats_dir.glob("*.json")):
            try:
                session = ChatSession.load(path)
                self._sessions.append(session)
            except (json.JSONDecodeError, KeyError) as e:
                log.warning("Skipping invalid chat file %s: %s", path, e)

    def new_session(self) -> ChatSession:
        session = ChatSession()
        self._sessions.append(session)
        return session

    def get_panel(self) -> pn.viewable.Viewable:
        """Tabs for each session plus ＋ New Chat button."""
        if not self._sessions:
            self._sessions.append(ChatSession())

        tabs = pn.Tabs(sizing_mode="stretch_both")

        def make_send_cb(sess: ChatSession):
            def cb(msg: str) -> None:
                if self.on_user_message:
                    self.on_user_message(sess, msg)

            return cb

        for session in self._sessions:
            panel = session.get_panel(
                self._chats_dir,
                on_send=make_send_cb(session),
            )
            tabs.append((session.title, panel))

        def add_new(_) -> None:
            sess = self.new_session()
            panel = sess.get_panel(
                self._chats_dir,
                on_send=make_send_cb(sess),
            )
            tabs.append((sess.title, panel))
            tabs.active = len(tabs) - 1

        new_btn = pn.widgets.Button(
            name="＋ New Chat",
            on_click=add_new,
            styles={"margin": "4px"},
        )

        voice_status = pn.pane.Markdown(
            "",
            stylesheets=["p { color: #4a90d9; font-size: 12px; margin: 0 8px; }"],
        )

        async def _clear_voice_status() -> None:
            await asyncio.sleep(3)
            voice_status.object = ""

        def on_mic_click(_) -> None:
            voice_status.object = "🎤 Voice input coming soon"
            asyncio.ensure_future(_clear_voice_status())

        mic_btn = pn.widgets.Button(
            name="🎤",
            on_click=on_mic_click,
            width=40,
            height=32,
            styles={"margin": "4px"},
            description="Voice input (coming soon)",
        )

        return pn.Column(
            pn.Row(new_btn, mic_btn, voice_status, sizing_mode="stretch_width"),
            tabs,
            sizing_mode="stretch_both",
            styles={
                "background": "#ffffff",
                "color": "#333333",
                "font-family": "system-ui, -apple-system, sans-serif",
            },
        )
