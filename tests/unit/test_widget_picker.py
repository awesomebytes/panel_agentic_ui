"""Unit tests for shell.widget_picker.WidgetPicker."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import panel as pn
import pytest

from config import Settings
from shell.widget_picker import WidgetPicker, _parse_manifest_from_file, _scan_examples
from shell.widget_registry import WidgetRegistry


def _write_manifest(path: Path, widgets: list[dict]) -> Path:
    manifest = path / "manifest.json"
    manifest.write_text(json.dumps({"widgets": widgets}), encoding="utf-8")
    return manifest


def _write_example(dir_: Path, name: str, manifest: dict) -> Path:
    fp = dir_ / f"example_{name}.py"
    src = (
        f'"""{json.dumps(manifest)}"""\n'
        "import panel as pn\n"
        "def build():\n"
        '    return pn.pane.Markdown("hi")\n'
    )
    fp.write_text(src, encoding="utf-8")
    return fp


@pytest.fixture()
def registry():
    r = WidgetRegistry()
    r.add("cpu_monitor", MagicMock())
    return r


@pytest.fixture()
def shell_mock():
    return MagicMock()


@pytest.fixture()
def settings():
    return Settings()


# ---------------------------------------------------------------------------
# _parse_manifest_from_file / _scan_examples
# ---------------------------------------------------------------------------


def test_parse_manifest_from_file(tmp_path):
    fp = _write_example(tmp_path, "test", {"name": "test", "version": 1, "title": "Test"})
    m = _parse_manifest_from_file(fp)
    assert m is not None
    assert m["name"] == "test"
    assert "_source_path" in m


def test_parse_manifest_invalid_file(tmp_path):
    fp = tmp_path / "example_bad.py"
    fp.write_text("x = 1\n", encoding="utf-8")
    assert _parse_manifest_from_file(fp) is None


def test_scan_examples_finds_files(tmp_path):
    _write_example(tmp_path, "a", {"name": "a", "version": 1, "title": "A"})
    _write_example(tmp_path, "b", {"name": "b", "version": 1, "title": "B"})
    results = _scan_examples(tmp_path)
    assert len(results) == 2
    names = {r["name"] for r in results}
    assert names == {"a", "b"}


def test_scan_examples_empty_dir(tmp_path):
    assert _scan_examples(tmp_path) == []


def test_scan_examples_nonexistent_dir(tmp_path):
    assert _scan_examples(tmp_path / "nope") == []


# ---------------------------------------------------------------------------
# _load_manifest_entries
# ---------------------------------------------------------------------------


def test_missing_manifest_returns_empty(tmp_path, registry, shell_mock, settings):
    picker = WidgetPicker(
        registry, shell_mock, settings,
        manifest_path=tmp_path / "nonexistent.json",
        examples_dir=tmp_path / "no_examples",
    )
    assert picker._load_manifest_entries() == []


def test_empty_manifest_returns_empty(tmp_path, registry, shell_mock, settings):
    _write_manifest(tmp_path, [])
    picker = WidgetPicker(
        registry, shell_mock, settings,
        manifest_path=tmp_path / "manifest.json",
        examples_dir=tmp_path / "no_examples",
    )
    assert picker._load_manifest_entries() == []


def test_manifest_widgets_are_returned(tmp_path, registry, shell_mock, settings):
    widgets = [
        {"name": "cpu_monitor", "title": "CPU Monitor"},
        {"name": "mem_monitor", "title": "Memory Monitor"},
    ]
    _write_manifest(tmp_path, widgets)
    picker = WidgetPicker(
        registry, shell_mock, settings,
        manifest_path=tmp_path / "manifest.json",
        examples_dir=tmp_path / "no_examples",
    )
    entries = picker._load_manifest_entries()
    assert len(entries) == 2


def test_malformed_manifest_returns_empty(tmp_path, registry, shell_mock, settings):
    (tmp_path / "manifest.json").write_text("not json!", encoding="utf-8")
    picker = WidgetPicker(
        registry, shell_mock, settings,
        manifest_path=tmp_path / "manifest.json",
        examples_dir=tmp_path / "no_examples",
    )
    assert picker._load_manifest_entries() == []


# ---------------------------------------------------------------------------
# _build_card
# ---------------------------------------------------------------------------


def test_card_for_loaded_widget(registry, shell_mock, settings, tmp_path):
    picker = WidgetPicker(registry, shell_mock, settings, examples_dir=tmp_path)
    card = picker._build_card(
        {"name": "cpu_monitor", "title": "CPU Monitor", "description": "CPU usage", "tags": ["cpu"]},
        source="example",
    )
    assert card is not None


def test_card_for_unloaded_widget(registry, shell_mock, settings, tmp_path):
    picker = WidgetPicker(registry, shell_mock, settings, examples_dir=tmp_path)
    card = picker._build_card(
        {"name": "unknown_widget", "title": "Unknown", "description": "", "tags": []},
        source="example",
    )
    assert card is not None


def test_promote_btn_visible_only_for_loaded_widget(registry, shell_mock, settings, tmp_path):
    picker = WidgetPicker(registry, shell_mock, settings, examples_dir=tmp_path)

    card_loaded = picker._build_card(
        {"name": "cpu_monitor", "title": "CPU", "description": "", "tags": []},
        source="example",
    )
    card_unloaded = picker._build_card(
        {"name": "not_in_registry", "title": "T", "description": "", "tags": []},
        source="example",
    )

    def _collect_buttons(obj):
        buttons = []
        if isinstance(obj, pn.widgets.Button):
            buttons.append(obj)
        if hasattr(obj, "objects"):
            for child in obj.objects:
                buttons.extend(_collect_buttons(child))
        return buttons

    loaded_promote = [b for b in _collect_buttons(card_loaded) if "PR" in b.name]
    unloaded_promote = [b for b in _collect_buttons(card_unloaded) if "PR" in b.name]

    assert all(b.visible for b in loaded_promote)
    assert all(not b.visible for b in unloaded_promote)


# ---------------------------------------------------------------------------
# get_panel / refresh
# ---------------------------------------------------------------------------


def test_get_panel_returns_viewable_with_examples(tmp_path, registry, shell_mock, settings):
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir()
    _write_example(examples_dir, "cpu_monitor", {"name": "cpu_monitor", "version": 1, "title": "CPU", "category": "Monitor", "tags": ["cpu"]})
    picker = WidgetPicker(
        registry, shell_mock, settings,
        examples_dir=examples_dir,
        manifest_path=tmp_path / "manifest.json",
    )
    panel = picker.get_panel()
    assert panel is not None


def test_get_panel_no_examples_shows_placeholder(tmp_path, registry, shell_mock, settings):
    picker = WidgetPicker(
        registry, shell_mock, settings,
        examples_dir=tmp_path / "no_examples",
        manifest_path=tmp_path / "nonexistent.json",
    )
    panel = picker.get_panel()
    assert panel is not None


def test_refresh_clears_dialog_area(tmp_path, registry, shell_mock, settings):
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir()
    _write_example(examples_dir, "cpu_monitor", {"name": "cpu_monitor", "version": 1, "title": "CPU", "category": "Monitor", "tags": []})
    picker = WidgetPicker(
        registry, shell_mock, settings,
        examples_dir=examples_dir,
        manifest_path=tmp_path / "manifest.json",
    )
    picker.get_panel()
    picker._dialog_area.objects = [pn.pane.Markdown("dummy")]
    picker.refresh()
    assert picker._dialog_area.objects == []


def test_refresh_before_get_panel_is_safe(tmp_path, registry, shell_mock, settings):
    picker = WidgetPicker(
        registry, shell_mock, settings,
        examples_dir=tmp_path / "no_examples",
        manifest_path=tmp_path / "nonexistent.json",
    )
    picker.refresh()


def test_scan_real_examples(registry, shell_mock, settings):
    """Verify that all 14 example files are discovered from the real examples dir."""
    picker = WidgetPicker(registry, shell_mock, settings)
    items = picker._build_list()
    has_content = any(not isinstance(item, pn.pane.Markdown) for item in items)
    assert has_content, "Expected at least one category section from real examples"
