"""Unit tests for shell.hot_load: hot_load, hot_load_with_fallback, update_manifest."""
import json
import sys

import panel as pn
import pytest

from shell.hot_load import hot_load, hot_load_with_fallback, update_manifest
from shell.widget_registry import WidgetRegistry

# ---------------------------------------------------------------------------
# Widget source templates
# ---------------------------------------------------------------------------

_VALID_SRC = '''\
"""
{
    "name": "foo",
    "version": 1,
    "title": "Foo Widget",
    "description": "Minimal test widget",
    "tags": ["foo"],
    "category": "test"
}
"""
import panel as pn


def build():
    return pn.pane.Markdown("hello")
'''

_VALID_SRC_V2 = '''\
"""
{
    "name": "foo",
    "version": 2,
    "title": "Foo Widget v2",
    "description": "Version 2 test widget",
    "tags": ["foo"],
    "category": "test"
}
"""
import panel as pn


def build():
    return pn.pane.Markdown("world")
'''

_BAD_BUILD_SRC = '''\
"""
{
    "name": "bad",
    "version": 1,
    "title": "Bad Widget",
    "description": "build() raises intentionally",
    "tags": [],
    "category": "test"
}
"""


def build():
    raise RuntimeError("intentional build error")
'''

_NO_BUILD_SRC = '''\
"""
{
    "name": "nobuild",
    "version": 1,
    "title": "No Build",
    "description": "Widget with no build() function",
    "tags": [],
    "category": "test"
}
"""
import panel as pn
'''

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _cleanup_test_modules():
    """Remove any widget_* modules injected into sys.modules during a test."""
    yield
    to_remove = [k for k in list(sys.modules) if k.startswith("widget_")]
    for key in to_remove:
        del sys.modules[key]


# ---------------------------------------------------------------------------
# hot_load
# ---------------------------------------------------------------------------


def test_load_valid_module_returns_callable_build(tmp_path):
    p = tmp_path / "widget_foo_v1.py"
    p.write_text(_VALID_SRC, encoding="utf-8")
    module = hot_load(p)
    assert callable(module.build)


def test_module_appears_in_sys_modules(tmp_path):
    p = tmp_path / "widget_foo_v1.py"
    p.write_text(_VALID_SRC, encoding="utf-8")
    hot_load(p)
    assert "widget_foo_v1" in sys.modules


def test_two_versions_coexist(tmp_path):
    p1 = tmp_path / "widget_foo_v1.py"
    p2 = tmp_path / "widget_foo_v2.py"
    p1.write_text(_VALID_SRC, encoding="utf-8")
    p2.write_text(_VALID_SRC_V2, encoding="utf-8")

    hot_load(p1)
    hot_load(p2)

    assert "widget_foo_v1" in sys.modules
    assert "widget_foo_v2" in sys.modules
    # Verify the two modules are distinct objects
    assert sys.modules["widget_foo_v1"] is not sys.modules["widget_foo_v2"]


def test_hot_load_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        hot_load(tmp_path / "widget_nonexistent_v1.py")


# ---------------------------------------------------------------------------
# hot_load_with_fallback — success path
# ---------------------------------------------------------------------------


def test_fallback_success_returns_component_and_no_error(tmp_path):
    p = tmp_path / "widget_foo_v1.py"
    p.write_text(_VALID_SRC, encoding="utf-8")
    registry = WidgetRegistry()

    component, err = hot_load_with_fallback(p, "foo", registry)

    assert err is None
    assert component is not None


# ---------------------------------------------------------------------------
# hot_load_with_fallback — failure paths
# ---------------------------------------------------------------------------


def test_fallback_returns_previous_version_on_crash(tmp_path):
    bad_file = tmp_path / "widget_foo_v2.py"
    bad_file.write_text(_BAD_BUILD_SRC, encoding="utf-8")

    registry = WidgetRegistry()
    previous = pn.pane.Markdown("previous version")
    registry.add("foo", previous)

    component, err = hot_load_with_fallback(bad_file, "foo", registry)

    assert err is not None
    assert "intentional build error" in err
    assert component is previous


def test_fallback_returns_error_pane_with_no_previous_version(tmp_path):
    bad_file = tmp_path / "widget_foo_v1.py"
    bad_file.write_text(_BAD_BUILD_SRC, encoding="utf-8")

    registry = WidgetRegistry()

    component, err = hot_load_with_fallback(bad_file, "foo", registry)

    assert err is not None
    assert isinstance(component, pn.pane.Markdown)


def test_fallback_no_build_attr_returns_error_pane(tmp_path):
    p = tmp_path / "widget_foo_v1.py"
    p.write_text(_NO_BUILD_SRC, encoding="utf-8")

    registry = WidgetRegistry()
    component, err = hot_load_with_fallback(p, "foo", registry)

    assert err is not None
    assert isinstance(component, pn.pane.Markdown)


# ---------------------------------------------------------------------------
# update_manifest
# ---------------------------------------------------------------------------


def test_manifest_created_with_first_entry(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    metadata = {
        "name": "test_widget",
        "version": 1,
        "title": "Test Widget",
        "description": "A test widget",
        "tags": ["test"],
        "category": "monitoring",
    }

    update_manifest(manifest_path, metadata)

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(data["widgets"]) == 1
    assert data["widgets"][0]["name"] == "test_widget"
    assert data["widgets"][0]["title"] == "Test Widget"


def test_manifest_update_replaces_existing_entry(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    meta_v1 = {
        "name": "foo",
        "version": 1,
        "title": "Foo v1",
        "description": "D",
        "tags": [],
        "category": "test",
    }
    meta_v2 = {
        "name": "foo",
        "version": 2,
        "title": "Foo v2",
        "description": "D",
        "tags": [],
        "category": "test",
    }

    update_manifest(manifest_path, meta_v1)
    update_manifest(manifest_path, meta_v2)

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    widgets = data["widgets"]
    assert len(widgets) == 1
    assert widgets[0]["version"] == 2
    assert widgets[0]["title"] == "Foo v2"


def test_manifest_appends_different_widgets(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    for i, name in enumerate(("alpha", "beta", "gamma"), start=1):
        update_manifest(
            manifest_path,
            {"name": name, "version": i, "title": name.title(), "description": "D", "tags": [], "category": "test"},
        )

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    names = {w["name"] for w in data["widgets"]}
    assert names == {"alpha", "beta", "gamma"}


def test_manifest_missing_name_key_raises(tmp_path):
    with pytest.raises(KeyError):
        update_manifest(tmp_path / "manifest.json", {"version": 1})
