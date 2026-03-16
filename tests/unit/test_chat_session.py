"""Unit tests for agent.chat_manager.ChatSession and ChatManager."""
import uuid

import pytest

from agent.chat_manager import ChatSession


def test_new_session_empty_history():
    """Fresh session has history == []."""
    session = ChatSession()
    assert session.history == []


def test_session_id_is_valid_uuid():
    """session_id is a valid UUID string."""
    session = ChatSession()
    uuid.UUID(session.session_id)  # should not raise


def test_add_user_message():
    """After add_message('user', 'hello'), history has one entry with role=user, content=hello."""
    session = ChatSession()
    session.add_message("user", "hello")
    assert len(session.history) == 1
    assert session.history[0]["role"] == "user"
    assert session.history[0]["content"] == "hello"


def test_add_assistant_message():
    """Same for role=assistant."""
    session = ChatSession()
    session.add_message("assistant", "Hi there!")
    assert len(session.history) == 1
    assert session.history[0]["role"] == "assistant"
    assert session.history[0]["content"] == "Hi there!"


def test_message_has_timestamp():
    """Each message has a timestamp that is a float > 0."""
    session = ChatSession()
    session.add_message("user", "test")
    assert "timestamp" in session.history[0]
    ts = session.history[0]["timestamp"]
    assert isinstance(ts, float)
    assert ts > 0


def test_persist_and_restore_roundtrip(tmp_path):
    """Save to tmp dir, load back; history and title match."""
    orig = ChatSession(title="My Chat")
    orig.add_message("user", "hello")
    orig.add_message("assistant", "world")
    orig.save(tmp_path)

    path = tmp_path / f"{orig.session_id}.json"
    restored = ChatSession.load(path)
    assert restored.session_id == orig.session_id
    assert restored.title == orig.title
    assert len(restored.history) == 2
    assert restored.history[0]["role"] == "user"
    assert restored.history[0]["content"] == "hello"
    assert restored.history[1]["role"] == "assistant"
    assert restored.history[1]["content"] == "world"


def test_restored_title_matches(tmp_path):
    """Explicit title check after roundtrip."""
    orig = ChatSession(title="Explicit Title")
    orig.add_message("user", "x")
    orig.save(tmp_path)

    path = tmp_path / f"{orig.session_id}.json"
    restored = ChatSession.load(path)
    assert restored.title == "Explicit Title"


def test_multiple_sessions_independent():
    """Two sessions have different IDs and independent histories."""
    s1 = ChatSession()
    s2 = ChatSession()
    assert s1.session_id != s2.session_id

    s1.add_message("user", "msg 1")
    s2.add_message("user", "msg 2")
    assert len(s1.history) == 1
    assert len(s2.history) == 1
    assert s1.history[0]["content"] == "msg 1"
    assert s2.history[0]["content"] == "msg 2"


def test_title_updates_on_first_user_message():
    """Title changes from 'New Chat' to first few words of first user message."""
    session = ChatSession()
    assert session.title == "New Chat"

    session.add_message("user", "Show me CPU usage across all cores")
    assert session.title != "New Chat"
    # Title should be derived from first few words
    assert "Show" in session.title or "CPU" in session.title
