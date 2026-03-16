"""Atomic save/load for GoldenLayout state, with named layout presets."""
import json
import re
from pathlib import Path

DEFAULT_LAYOUT = {
    "root": {
        "type": "row",
        "content": [
            {
                "type": "stack",
                "size": "75%",
                "content": []
            },
            {
                "type": "stack",
                "size": "25%",
                "content": []
            }
        ]
    }
}

# ---------------------------------------------------------------------------
# Built-in presets
# ---------------------------------------------------------------------------

_PRESET_MONITORING = {
    "root": {
        "type": "row",
        "content": [
            {
                "type": "stack",
                "size": "65%",
                "content": [
                    {
                        "type": "component",
                        "componentType": "panel-widget",
                        "componentState": {"widget_name": "welcome"},
                        "title": "Welcome",
                        "isClosable": True,
                    }
                ],
            },
            {
                "type": "stack",
                "size": "35%",
                "content": [
                    {
                        "type": "component",
                        "componentType": "panel-widget",
                        "componentState": {"widget_name": "__chat__"},
                        "title": "Chat",
                        "isClosable": True,
                    }
                ],
            },
        ],
    }
}

_PRESET_DEBUG = {
    "root": {
        "type": "column",
        "content": [
            {
                "type": "row",
                "size": "65%",
                "content": [
                    {
                        "type": "stack",
                        "size": "65%",
                        "content": [
                            {
                                "type": "component",
                                "componentType": "panel-widget",
                                "componentState": {"widget_name": "welcome"},
                                "title": "Welcome",
                                "isClosable": True,
                            }
                        ],
                    },
                    {
                        "type": "stack",
                        "size": "35%",
                        "content": [
                            {
                                "type": "component",
                                "componentType": "panel-widget",
                                "componentState": {"widget_name": "__chat__"},
                                "title": "Chat",
                                "isClosable": True,
                            }
                        ],
                    },
                ],
            },
            {
                "type": "stack",
                "size": "35%",
                "content": [
                    {
                        "type": "component",
                        "componentType": "panel-widget",
                        "componentState": {"widget_name": "repl"},
                        "title": "REPL",
                        "isClosable": True,
                    }
                ],
            },
        ],
    }
}

_PRESET_MINIMAL = {
    "root": {
        "type": "stack",
        "content": [
            {
                "type": "component",
                "componentType": "panel-widget",
                "componentState": {"widget_name": "welcome"},
                "title": "Welcome",
                "isClosable": False,
            }
        ],
    }
}

_BUILTIN_PRESETS: dict[str, dict] = {
    "monitoring": _PRESET_MONITORING,
    "debug": _PRESET_DEBUG,
    "minimal": _PRESET_MINIMAL,
}

_PRESET_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


class LayoutStateManager:
    """Manages GoldenLayout config persistence with atomic writes."""

    def __init__(self, path: Path | str = "layout.json"):
        self._path = Path(path)

    # ------------------------------------------------------------------
    # Active layout
    # ------------------------------------------------------------------

    def save(self, layout_json: str) -> None:
        """Atomic write: write to tmp file then rename."""
        try:
            json.loads(layout_json)
        except (json.JSONDecodeError, TypeError):
            return
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(layout_json)
        tmp.rename(self._path)

    def load(self) -> str:
        """Load layout from disk, falling back to default if missing/invalid."""
        if not self._path.exists():
            return json.dumps(DEFAULT_LAYOUT)
        try:
            text = self._path.read_text()
            json.loads(text)
            return text
        except (json.JSONDecodeError, OSError):
            return json.dumps(DEFAULT_LAYOUT)

    @property
    def default_json(self) -> str:
        return json.dumps(DEFAULT_LAYOUT)

    # ------------------------------------------------------------------
    # Named presets
    # ------------------------------------------------------------------

    def _preset_path(self, name: str) -> Path:
        return self._path.parent / f"layout_{name}.json"

    def save_preset(self, name: str, layout_json: str) -> None:
        """Save *layout_json* as a named preset (layout_<name>.json).

        Silently returns if *layout_json* is invalid JSON or *name* contains
        characters outside ``[a-zA-Z0-9_-]``.
        """
        if not _PRESET_NAME_RE.match(name):
            return
        try:
            json.loads(layout_json)
        except (json.JSONDecodeError, TypeError):
            return
        path = self._preset_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(layout_json, encoding="utf-8")
        tmp.rename(path)

    def load_preset(self, name: str) -> str | None:
        """Return the preset JSON string for *name*, or ``None`` if unknown.

        File-based presets take precedence over built-ins.
        """
        path = self._preset_path(name)
        if path.exists():
            try:
                text = path.read_text(encoding="utf-8")
                json.loads(text)
                return text
            except (json.JSONDecodeError, OSError):
                pass
        if name in _BUILTIN_PRESETS:
            return json.dumps(_BUILTIN_PRESETS[name])
        return None

    def list_presets(self) -> list[str]:
        """Return sorted list of available preset names (built-ins + on-disk)."""
        names: set[str] = set(_BUILTIN_PRESETS.keys())
        for p in self._path.parent.glob("layout_*.json"):
            stem = p.stem  # e.g. "layout_my_preset"
            preset_name = stem[len("layout_"):]
            if preset_name and _PRESET_NAME_RE.match(preset_name):
                names.add(preset_name)
        return sorted(names)
