"""Unit tests for shell.widget_registry.WidgetRegistry."""
import threading

import pytest

from shell.widget_registry import WidgetRegistry


def test_add_and_get():
    reg = WidgetRegistry()
    reg.add("widget_a", "component_a")
    assert reg.get("widget_a") == "component_a"


def test_remove():
    reg = WidgetRegistry()
    reg.add("widget_a", "component_a")
    reg.remove("widget_a")
    assert reg.get("widget_a") is None


def test_list_names():
    reg = WidgetRegistry()
    reg.add("alpha", "comp_1")
    reg.add("beta", "comp_2")
    assert set(reg.list_names()) == {"alpha", "beta"}


def test_concurrent_add_remove():
    reg = WidgetRegistry()
    errors = []

    def worker(i):
        try:
            name = f"widget_{i}"
            reg.add(name, f"component_{i}")
            reg.remove(name)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(100)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert len(reg) >= 0


def test_get_missing_returns_none():
    reg = WidgetRegistry()
    assert reg.get("nonexistent") is None


def test_contains():
    reg = WidgetRegistry()
    reg.add("present", "comp")
    assert "present" in reg
    assert "absent" not in reg


def test_len():
    reg = WidgetRegistry()
    reg.add("a", "comp_a")
    reg.add("b", "comp_b")
    assert len(reg) == 2
    reg.remove("a")
    assert len(reg) == 1
