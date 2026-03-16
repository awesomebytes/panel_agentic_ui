"""Unit tests for agent.generator: extract_code and generate_and_load."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent.chat_manager import ChatSession
from agent.generator import extract_code, generate_and_load
from config import Settings
from shell.widget_registry import WidgetRegistry


# ---------------------------------------------------------------------------
# Widget source fixtures
# ---------------------------------------------------------------------------

VALID_WIDGET_SRC = '''\
"""
{
    "name": "test_widget",
    "version": 1,
    "title": "Test Widget",
    "description": "A generated test widget",
    "tags": ["test"],
    "category": "monitoring"
}
"""
import panel as pn


def build():
    return pn.pane.Markdown("hello from test widget")
'''

# Missing build() — fails AST validation with "build() function" error
INVALID_WIDGET_SRC = '''\
"""
{
    "name": "test_widget",
    "version": 1,
    "title": "Test Widget",
    "description": "A generated test widget",
    "tags": ["test"],
    "category": "monitoring"
}
"""
import panel as pn
'''


def _in_fence(src: str) -> str:
    return f"Here is your widget:\n\n```python\n{src}\n```\n"


# ---------------------------------------------------------------------------
# MockProvider
# ---------------------------------------------------------------------------


class MockProvider:
    """Returns predefined responses in sequence, recording all calls."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, list[dict]]] = []

    async def complete(self, system: str, messages: list[dict]) -> str:
        self.calls.append((system, messages))
        return self._responses.pop(0)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _cleanup_widget_modules():
    yield
    for key in [k for k in list(sys.modules) if k.startswith("widget_")]:
        del sys.modules[key]


def _settings(tmp_path: Path) -> Settings:
    return Settings(widgets_dir=str(tmp_path))


def _session(text: str = "create a test widget") -> ChatSession:
    s = ChatSession()
    s.add_message("user", text)
    return s


def _shell() -> MagicMock:
    m = MagicMock()
    m.add_widget = MagicMock()
    return m


# ---------------------------------------------------------------------------
# extract_code
# ---------------------------------------------------------------------------


def test_extract_code_from_response():
    response = "Here is the widget:\n\n```python\nprint('hello')\n```\n"
    result = extract_code(response)
    assert result is not None
    assert "print('hello')" in result


def test_extract_code_no_block():
    assert extract_code("There is no code block here.") is None


def test_extract_code_generic_block():
    # A plain ``` block without 'python' tag should NOT be matched by _CODE_FENCE_RE
    assert extract_code("```\nprint('hello')\n```") is None


# ---------------------------------------------------------------------------
# generate_and_load — success
# ---------------------------------------------------------------------------


async def test_generates_and_loads_valid_widget(tmp_path):
    provider = MockProvider([_in_fence(VALID_WIDGET_SRC)])
    session = _session()
    registry = WidgetRegistry()

    with patch("agent.generator.get_provider", return_value=provider):
        result = await generate_and_load(
            "create a test widget", session, _shell(), registry, _settings(tmp_path)
        )

    assert result is True
    assert list(tmp_path.glob("widget_test_widget_v1.py")), "widget file not written"
    assert "test_widget" in registry.list_names()


# ---------------------------------------------------------------------------
# generate_and_load — self-correction
# ---------------------------------------------------------------------------


async def test_self_corrects_on_first_failure(tmp_path):
    provider = MockProvider([_in_fence(INVALID_WIDGET_SRC), _in_fence(VALID_WIDGET_SRC)])
    session = _session()
    registry = WidgetRegistry()

    with patch("agent.generator.get_provider", return_value=provider):
        result = await generate_and_load(
            "create a test widget", session, _shell(), registry, _settings(tmp_path)
        )

    assert result is True
    assert len(provider.calls) == 2


async def test_fails_after_max_retries(tmp_path):
    provider = MockProvider([
        _in_fence(INVALID_WIDGET_SRC),
        _in_fence(INVALID_WIDGET_SRC),
        _in_fence(INVALID_WIDGET_SRC),
    ])
    session = _session()
    registry = WidgetRegistry()

    with patch("agent.generator.get_provider", return_value=provider):
        result = await generate_and_load(
            "create a test widget", session, _shell(), registry, _settings(tmp_path)
        )

    assert result is False
    assert len(provider.calls) == 3  # exhausted MAX_RETRIES


# ---------------------------------------------------------------------------
# generate_and_load — retry prompt contains error text
# ---------------------------------------------------------------------------


async def test_error_in_retry_prompt(tmp_path):
    provider = MockProvider([_in_fence(INVALID_WIDGET_SRC), _in_fence(VALID_WIDGET_SRC)])
    session = _session()

    with patch("agent.generator.get_provider", return_value=provider):
        await generate_and_load(
            "create a test widget", session, _shell(), WidgetRegistry(), _settings(tmp_path)
        )

    assert len(provider.calls) == 2
    _, retry_messages = provider.calls[1]
    last_user = next(m for m in reversed(retry_messages) if m["role"] == "user")
    # The validator error for missing build() must appear in the retry prompt
    assert "build()" in last_user["content"]


# ---------------------------------------------------------------------------
# generate_and_load — manifest
# ---------------------------------------------------------------------------


async def test_manifest_updated_after_success(tmp_path):
    provider = MockProvider([_in_fence(VALID_WIDGET_SRC)])

    with patch("agent.generator.get_provider", return_value=provider):
        await generate_and_load(
            "create a test widget", _session(), _shell(), WidgetRegistry(), _settings(tmp_path)
        )

    manifest_path = tmp_path / "manifest.json"
    assert manifest_path.exists()
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert any(w["name"] == "test_widget" for w in data["widgets"])


# ---------------------------------------------------------------------------
# generate_and_load — session history
# ---------------------------------------------------------------------------


async def test_session_gets_success_message(tmp_path):
    provider = MockProvider([_in_fence(VALID_WIDGET_SRC)])
    session = _session()

    with patch("agent.generator.get_provider", return_value=provider):
        await generate_and_load(
            "create a test widget", session, _shell(), WidgetRegistry(), _settings(tmp_path)
        )

    assistant_msgs = [m for m in session.history if m["role"] == "assistant"]
    assert assistant_msgs, "no assistant message added on success"
    assert any("Test Widget" in m["content"] for m in assistant_msgs)


async def test_session_gets_error_after_max_retries(tmp_path):
    provider = MockProvider([
        _in_fence(INVALID_WIDGET_SRC),
        _in_fence(INVALID_WIDGET_SRC),
        _in_fence(INVALID_WIDGET_SRC),
    ])
    session = _session()

    with patch("agent.generator.get_provider", return_value=provider):
        await generate_and_load(
            "create a test widget", session, _shell(), WidgetRegistry(), _settings(tmp_path)
        )

    assistant_msgs = [m for m in session.history if m["role"] == "assistant"]
    assert assistant_msgs, "no assistant message added on failure"
    last_content = assistant_msgs[-1]["content"].lower()
    assert "failed" in last_content
