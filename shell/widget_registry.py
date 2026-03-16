"""Thread-safe widget registry for Panel components."""
import threading
from typing import Any


class WidgetRegistry:
    """Thread-safe dictionary mapping widget names to Panel components."""

    def __init__(self):
        self._lock = threading.Lock()
        self._widgets: dict[str, Any] = {}

    def add(self, name: str, component: Any) -> None:
        with self._lock:
            self._widgets[name] = component

    def remove(self, name: str) -> Any | None:
        with self._lock:
            return self._widgets.pop(name, None)

    def get(self, name: str) -> Any | None:
        with self._lock:
            return self._widgets.get(name)

    def list_names(self) -> list[str]:
        with self._lock:
            return list(self._widgets.keys())

    def __contains__(self, name: str) -> bool:
        with self._lock:
            return name in self._widgets

    def __len__(self) -> int:
        with self._lock:
            return len(self._widgets)
