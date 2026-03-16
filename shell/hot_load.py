"""Versioned module loader for Panel widgets."""
import importlib.util
import json
import re
import sys
import tempfile
import traceback
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

import panel as pn

from shell.widget_registry import WidgetRegistry


def hot_load(path: Path) -> ModuleType:
    """Load a Python file as a versioned module.

    The module name is derived from the file stem (e.g. widget_cpu_v2.py ->
    widget_cpu_v2). The module is inserted into sys.modules so subsequent
    imports resolve correctly without reload.

    Args:
        path: Absolute or relative path to the .py widget file.

    Returns:
        The loaded module.

    Raises:
        FileNotFoundError: If path does not exist.
        Exception: Any error raised during module execution.
    """
    path = Path(path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Widget file not found: {path}")

    module_name = path.stem
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot create module spec for {path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def hot_load_with_fallback(
    path: Path,
    name: str,
    registry: WidgetRegistry,
) -> tuple[Any, str | None]:
    """Load a widget module and call its build() function, with fallback.

    On success returns (component, None).
    On failure, returns the previously registered component if available,
    otherwise an error pane.  The error message is always returned as the
    second element on failure.

    Args:
        path: Path to the versioned widget .py file.
        name: Canonical widget name used as the registry key.
        registry: Live WidgetRegistry instance.

    Returns:
        A (component, error_message) tuple.  error_message is None on success.
    """
    try:
        module = hot_load(path)
        if not hasattr(module, "build"):
            raise AttributeError(f"Widget module '{path.stem}' has no build() function")
        component = module.build()
        return component, None
    except Exception:
        error_message = traceback.format_exc()
        if name in registry:
            return registry.get(name), error_message
        error_pane = pn.pane.Markdown(
            f'<span style="color:red; white-space:pre-wrap;">'
            f"**Widget load error**\n\n```\n{error_message}\n```"
            f"</span>",
            sizing_mode="stretch_width",
        )
        return error_pane, error_message


def _extract_version(stem: str) -> int:
    """Extract version number from a file stem like 'widget_foo_v3'."""
    match = re.search(r"_v(\d+)$", stem)
    return int(match.group(1)) if match else 0


def update_manifest(manifest_path: Path, metadata: dict) -> None:
    """Atomically update widgets/manifest.json with a widget entry.

    Reads the current manifest, adds or replaces the entry whose "name" field
    matches metadata["name"], then writes back atomically via a temp file and
    os.replace.  Also appends an entry to the per-widget ``version_history``
    array: ``[{version, filename, timestamp}, ...]``.

    Args:
        manifest_path: Path to manifest.json.
        metadata: Dict containing at minimum a "name" key.

    Raises:
        KeyError: If metadata does not contain a "name" key.
        json.JSONDecodeError: If the existing manifest is malformed.
    """
    if "name" not in metadata:
        raise KeyError("metadata must contain a 'name' key")

    manifest_path = Path(manifest_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    if manifest_path.exists():
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        data = {"widgets": []}

    widgets: list[dict] = data.setdefault("widgets", [])

    name = metadata["name"]
    version = metadata.get("version")
    timestamp = datetime.now(tz=timezone.utc).isoformat()
    new_ver_entry = {
        "version": version,
        "filename": f"widget_{name}_v{version}.py",
        "timestamp": timestamp,
    }

    for i, entry in enumerate(widgets):
        if entry.get("name") == name:
            history: list[dict] = list(entry.get("version_history", []))
            history = [v for v in history if v.get("version") != version]
            history.append(new_ver_entry)
            new_entry = dict(metadata)
            new_entry["version_history"] = history
            widgets[i] = new_entry
            break
    else:
        new_entry = dict(metadata)
        new_entry["version_history"] = [new_ver_entry]
        widgets.append(new_entry)

    # Atomic write: write to a sibling temp file then replace
    dir_ = manifest_path.parent
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=dir_,
        delete=False,
        suffix=".tmp",
    ) as tmp:
        json.dump(data, tmp, indent=2)
        tmp_path = Path(tmp.name)

    tmp_path.replace(manifest_path)


def get_widget_versions(manifest_path: Path, name: str) -> list[dict]:
    """Return the version history for a widget from the manifest.

    Args:
        manifest_path: Path to manifest.json.
        name: Widget name (snake_case).

    Returns:
        List of ``{version, filename, timestamp}`` dicts ordered oldest-first
        as stored; returns ``[]`` if the manifest or widget is not found.
    """
    manifest_path = Path(manifest_path)
    if not manifest_path.exists():
        return []
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in data.get("widgets", []):
        if entry.get("name") == name:
            return list(entry.get("version_history", []))
    return []


def cleanup_old_versions(
    widgets_dir: Path, name: str, keep: int = 10
) -> list[Path]:
    """Delete old versioned widget files, keeping only the *keep* most recent.

    Scans ``widgets_dir`` for files matching ``widget_<name>_v*.py``, sorts
    them by version number, and deletes all but the newest ``keep`` files.

    Args:
        widgets_dir: Directory containing the versioned widget ``.py`` files.
        name: Widget name (snake_case), matching the ``widget_<name>_v*.py``
            naming convention.
        keep: How many recent versions to retain (default: 10).

    Returns:
        List of ``Path`` objects that were successfully deleted.
    """
    widgets_dir = Path(widgets_dir)
    files = sorted(
        widgets_dir.glob(f"widget_{name}_v*.py"),
        key=lambda p: _extract_version(p.stem),
    )
    to_delete = files[:-keep] if len(files) > keep else []
    deleted: list[Path] = []
    for f in to_delete:
        try:
            f.unlink()
            deleted.append(f)
        except OSError:
            pass
    return deleted
