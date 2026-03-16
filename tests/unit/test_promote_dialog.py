"""Unit tests for shell.promote_dialog.PromoteDialog."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from config import Settings
from shell.promote_dialog import PromoteDialog
from shell.widget_registry import WidgetRegistry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _settings(**overrides) -> Settings:
    base = dict(github_token="ghp_test", github_repo="owner/repo")
    base.update(overrides)
    return Settings(**base)


@pytest.fixture()
def registry():
    r = WidgetRegistry()
    r.add("cpu_monitor", MagicMock())
    return r


# ---------------------------------------------------------------------------
# Construction / get_panel
# ---------------------------------------------------------------------------


def test_get_panel_returns_viewable(registry):
    dialog = PromoteDialog("cpu_monitor", registry, _settings())
    panel = dialog.get_panel()
    assert panel is not None


def test_visible_param_default_false(registry):
    dialog = PromoteDialog("cpu_monitor", registry, _settings())
    assert dialog.visible is False


def test_unconfigured_no_token_does_not_crash(registry):
    dialog = PromoteDialog(
        "cpu_monitor", registry, Settings(github_token="", github_repo="")
    )
    panel = dialog.get_panel()
    assert panel is not None


def test_unconfigured_bad_repo_format_does_not_crash(registry):
    dialog = PromoteDialog(
        "cpu_monitor",
        registry,
        Settings(github_token="tok", github_repo="not-valid-format"),
    )
    panel = dialog.get_panel()
    assert panel is not None


# ---------------------------------------------------------------------------
# _resolve_widget_path
# ---------------------------------------------------------------------------


def test_resolve_widget_path_finds_versioned_file(tmp_path, registry):
    widget_file = tmp_path / "widget_cpu_monitor_v1.py"
    widget_file.write_text("# widget", encoding="utf-8")
    s = _settings(widgets_dir=tmp_path)
    dialog = PromoteDialog("cpu_monitor", registry, s)
    assert dialog._resolve_widget_path() == widget_file


def test_resolve_widget_path_picks_latest_version(tmp_path, registry):
    (tmp_path / "widget_cpu_monitor_v1.py").write_text("# v1", encoding="utf-8")
    v2 = tmp_path / "widget_cpu_monitor_v2.py"
    v2.write_text("# v2", encoding="utf-8")
    s = _settings(widgets_dir=tmp_path)
    dialog = PromoteDialog("cpu_monitor", registry, s)
    assert dialog._resolve_widget_path() == v2


def test_resolve_widget_path_raises_when_missing(tmp_path, registry):
    s = _settings(widgets_dir=tmp_path)
    dialog = PromoteDialog("no_such_widget", registry, s)
    with pytest.raises(FileNotFoundError):
        dialog._resolve_widget_path()


def test_explicit_widget_path_preferred(tmp_path, registry):
    explicit = tmp_path / "widget_cpu_monitor_v9.py"
    explicit.write_text("# v9", encoding="utf-8")
    # Also plant a v1 to confirm explicit wins
    (tmp_path / "widget_cpu_monitor_v1.py").write_text("# v1", encoding="utf-8")
    dialog = PromoteDialog("cpu_monitor", registry, _settings(), widget_path=explicit)
    assert dialog._resolve_widget_path() == explicit
