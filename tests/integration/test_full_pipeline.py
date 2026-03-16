"""Integration tests: full generate → validate → hot_load pipeline with mocked LLM."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent.chat_manager import ChatSession
from agent.generator import generate_and_load
from config import Settings
from shell.widget_registry import WidgetRegistry


# ---------------------------------------------------------------------------
# Widget source fixtures
# ---------------------------------------------------------------------------

VALID_WIDGET_SRC = '''\
"""
{
    "name": "pipeline_widget",
    "version": 1,
    "title": "Pipeline Widget",
    "description": "Integration test widget",
    "tags": ["test"],
    "category": "monitoring"
}
"""
import panel as pn


def build():
    return pn.pane.Markdown("integration test widget")
'''

INVALID_WIDGET_SRC = '''\
"""
{
    "name": "pipeline_widget",
    "version": 1,
    "title": "Pipeline Widget",
    "description": "Integration test widget",
    "tags": ["test"],
    "category": "monitoring"
}
"""
import panel as pn
'''


def _in_fence(src: str) -> str:
    return f"Here is your widget:\n\n```python\n{src}\n```\n"


# ---------------------------------------------------------------------------
# MockProvider (same pattern as unit tests)
# ---------------------------------------------------------------------------


class MockProvider:
    """Returns predefined responses in sequence."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, list[dict]]] = []

    async def complete(self, system: str, messages: list[dict]) -> str:
        self.calls.append((system, messages))
        return self._responses.pop(0)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _cleanup_widget_modules():
    yield
    for key in [k for k in list(sys.modules) if k.startswith("widget_")]:
        del sys.modules[key]


def _settings(tmp_path: Path) -> Settings:
    return Settings(widgets_dir=str(tmp_path))


def _session(text: str = "create a pipeline widget") -> ChatSession:
    s = ChatSession()
    s.add_message("user", text)
    return s


def _shell() -> MagicMock:
    m = MagicMock()
    m.add_widget = MagicMock()
    return m


# ---------------------------------------------------------------------------
# test_message_generates_valid_widget
# ---------------------------------------------------------------------------


async def test_message_generates_valid_widget(tmp_path):
    """Mock returns valid code → widget file written to disk and added to registry."""
    provider = MockProvider([_in_fence(VALID_WIDGET_SRC)])
    session = _session()
    registry = WidgetRegistry()

    with patch("agent.generator.get_provider", return_value=provider):
        result = await generate_and_load(
            "create a pipeline widget", session, _shell(), registry, _settings(tmp_path)
        )

    assert result is True

    written = list(tmp_path.glob("widget_pipeline_widget_v1.py"))
    assert written, "widget .py file was not written to disk"
    assert "pipeline_widget" in registry.list_names(), "widget not added to registry"

    manifest_path = tmp_path / "manifest.json"
    assert manifest_path.exists(), "manifest.json was not created"
    data = json.loads(manifest_path.read_text())
    assert any(w["name"] == "pipeline_widget" for w in data["widgets"])

    assistant_msgs = [m for m in session.history if m["role"] == "assistant"]
    assert assistant_msgs
    assert any("Pipeline Widget" in m["content"] for m in assistant_msgs)


# ---------------------------------------------------------------------------
# test_invalid_code_retried_and_succeeds
# ---------------------------------------------------------------------------


async def test_invalid_code_retried_and_succeeds(tmp_path):
    """First response fails validation; second is valid → still returns True."""
    provider = MockProvider([_in_fence(INVALID_WIDGET_SRC), _in_fence(VALID_WIDGET_SRC)])
    session = _session()
    registry = WidgetRegistry()

    with patch("agent.generator.get_provider", return_value=provider):
        result = await generate_and_load(
            "create a pipeline widget", session, _shell(), registry, _settings(tmp_path)
        )

    assert result is True
    assert len(provider.calls) == 2, f"expected 2 LLM calls, got {len(provider.calls)}"
    assert "pipeline_widget" in registry.list_names()

    # Retry prompt must contain the validation error
    _, retry_messages = provider.calls[1]
    last_user = next(m for m in reversed(retry_messages) if m["role"] == "user")
    assert "build()" in last_user["content"]


# ---------------------------------------------------------------------------
# test_three_failures_no_crash
# ---------------------------------------------------------------------------


async def test_three_failures_no_crash(tmp_path):
    """Three consecutive invalid responses → returns False, no exception raised."""
    provider = MockProvider([
        _in_fence(INVALID_WIDGET_SRC),
        _in_fence(INVALID_WIDGET_SRC),
        _in_fence(INVALID_WIDGET_SRC),
    ])
    session = _session()
    registry = WidgetRegistry()

    with patch("agent.generator.get_provider", return_value=provider):
        result = await generate_and_load(
            "create a pipeline widget", session, _shell(), registry, _settings(tmp_path)
        )

    assert result is False
    assert len(provider.calls) == 3
    assert registry.list_names() == [], "registry should be empty after all failures"

    assistant_msgs = [m for m in session.history if m["role"] == "assistant"]
    assert assistant_msgs
    assert any("failed" in m["content"].lower() for m in assistant_msgs)


# ---------------------------------------------------------------------------
# test_cleanup_runs_after_success
# ---------------------------------------------------------------------------


async def test_cleanup_runs_after_success(tmp_path):
    """After success, versions beyond keep=10 are deleted from disk."""
    # Pre-create 12 old version files for the same widget name
    for v in range(1, 13):
        (tmp_path / f"widget_pipeline_widget_v{v}.py").write_text(
            f"# stub version {v}\n", encoding="utf-8"
        )

    # The new generation writes v13 (we override the source to use version 13)
    versioned_src = VALID_WIDGET_SRC.replace('"version": 1', '"version": 13')
    provider = MockProvider([_in_fence(versioned_src)])
    session = _session()
    registry = WidgetRegistry()

    with patch("agent.generator.get_provider", return_value=provider):
        result = await generate_and_load(
            "create a pipeline widget", session, _shell(), registry, _settings(tmp_path)
        )

    assert result is True

    remaining = sorted(
        tmp_path.glob("widget_pipeline_widget_v*.py"),
        key=lambda p: int(p.stem.split("_v")[-1]),
    )
    versions_kept = [int(p.stem.split("_v")[-1]) for p in remaining]

    assert len(versions_kept) <= 10, (
        f"Expected ≤10 versions kept, but found {len(versions_kept)}: {versions_kept}"
    )
    # The newest version must always be present
    assert 13 in versions_kept, "latest version (v13) was incorrectly deleted"
