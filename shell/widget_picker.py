"""Widget Picker — browse premade example widgets and generated widgets; add or promote them."""
from __future__ import annotations

import ast
import json
import logging
import shutil
from pathlib import Path
from typing import Any

import panel as pn
import param

from config import Settings
from shell.hot_load import hot_load_with_fallback, update_manifest
from shell.promote_dialog import PromoteDialog

log = logging.getLogger(__name__)

_CARD_CSS = """
.wp-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 12px 14px;
    margin-bottom: 8px;
    transition: box-shadow 0.15s;
}
.wp-card:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
.wp-tag {
    display: inline-block;
    background: #e8f0fe;
    color: #1a73e8;
    border-radius: 3px;
    padding: 1px 6px;
    font-size: 11px;
    margin-right: 4px;
}
.wp-cat {
    display: inline-block;
    background: #f0f0f0;
    color: #666;
    border-radius: 3px;
    padding: 1px 6px;
    font-size: 11px;
    margin-left: 8px;
}
"""

_CONTAINER_STYLES = {
    "background": "#ffffff",
    "font-family": "system-ui, -apple-system, sans-serif",
    "padding": "10px",
}


def _parse_manifest_from_file(path: Path) -> dict | None:
    """Extract MANIFEST JSON from a Python file's module docstring via AST."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if not tree.body:
            return None
        first = tree.body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
            raw = first.value.value
            if isinstance(raw, str) and raw.strip().startswith("{"):
                manifest = json.loads(raw)
                manifest["_source_path"] = str(path)
                return manifest
    except Exception as exc:
        log.debug("Could not parse manifest from %s: %s", path.name, exc)
    return None


def _scan_examples(examples_dir: Path) -> list[dict]:
    """Scan example_*.py files and return their parsed MANIFEST dicts."""
    if not examples_dir.is_dir():
        return []
    results = []
    for fp in sorted(examples_dir.glob("example_*.py")):
        manifest = _parse_manifest_from_file(fp)
        if manifest and "name" in manifest:
            results.append(manifest)
    return results


class WidgetPicker(param.Parameterized):
    """Panel component for browsing premade example widgets and generated widgets.

    Premade widgets are scanned from agent/prompts/examples/.
    Generated widgets are read from manifest.json.
    Users can add any widget to the GoldenLayout shell with one click.
    """

    def __init__(
        self,
        registry: Any,
        shell: Any,
        settings: Settings | None = None,
        examples_dir: Path | str | None = None,
        widgets_dir: Path | str | None = None,
        manifest_path: Path | str | None = None,
        **params: Any,
    ) -> None:
        super().__init__(**params)
        self._registry = registry
        self._shell = shell

        if settings is None:
            from config import settings as _settings
            settings = _settings
        self._settings = settings

        self._examples_dir = Path(examples_dir) if examples_dir else Path("agent/prompts/examples")
        self._widgets_dir = Path(widgets_dir) if widgets_dir else Path(settings.widgets_dir)
        self._manifest_path = (
            Path(manifest_path) if manifest_path else self._widgets_dir / "manifest.json"
        )
        self._dialog_area = pn.Column(sizing_mode="stretch_width")
        self._list_col: pn.Column | None = None
        self._status = pn.pane.Markdown("", sizing_mode="stretch_width", margin=(0, 0))

    def _load_manifest_entries(self) -> list[dict]:
        """Load widgets from manifest.json (generated widgets)."""
        if not self._manifest_path.exists():
            return []
        try:
            data = json.loads(self._manifest_path.read_text(encoding="utf-8"))
            return data.get("widgets", [])
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("WidgetPicker: could not read manifest: %s", exc)
            return []

    def _build_card(self, entry: dict, source: str) -> pn.viewable.Viewable:
        """Build a card row for one widget entry.

        source: "example" or "generated"
        """
        name: str = entry.get("name", "")
        title: str = entry.get("title", name)
        description: str = entry.get("description", "")
        category: str = entry.get("category", "")
        tags: list[str] = entry.get("tags", [])
        is_loaded = name in self._registry

        tags_html = "".join(f'<span class="wp-tag">{t}</span>' for t in tags[:5])
        cat_html = f'<span class="wp-cat">{category}</span>' if category else ""
        source_badge = (
            '<span class="wp-tag" style="background:#e8fee8;color:#2d7d2d">premade</span>'
            if source == "example"
            else '<span class="wp-tag" style="background:#fff3e0;color:#e65100">generated</span>'
        )

        info_html = pn.pane.HTML(
            f"<div><strong>{title}</strong>{cat_html} {source_badge}</div>"
            f"<div style='color:#666;font-size:12px;margin:3px 0'>{description}</div>"
            f"<div>{tags_html}</div>",
            sizing_mode="stretch_width",
            margin=(0, 0),
        )

        add_btn = pn.widgets.Button(
            name="✓ Added" if is_loaded else "Add",
            button_type="success" if is_loaded else "primary",
            disabled=is_loaded,
            width=80,
            height=30,
            margin=(0, 4, 0, 0),
        )
        promote_btn = pn.widgets.Button(
            name="⬆ PR",
            button_type="light",
            width=60,
            height=30,
            margin=(0, 0),
            visible=is_loaded,
        )

        def _on_add(_evt: Any, _entry=entry, _source=source, _btn=add_btn) -> None:
            try:
                if _source == "example":
                    src_path = Path(_entry["_source_path"])
                    version = _entry.get("version", 1)
                    dest_name = f"widget_{name}_v{version}.py"
                    dest_path = self._widgets_dir / dest_name
                    self._widgets_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_path, dest_path)
                    component, err = hot_load_with_fallback(dest_path, name, self._registry)
                    if err:
                        self._status.object = f"<span style='color:red'>Error loading {name}: {err[:120]}</span>"
                        return
                    self._registry.add(name, component)
                    update_manifest(self._manifest_path, _entry)
                else:
                    if name not in self._registry:
                        self._status.object = f"<span style='color:orange'>Widget {name} is not loaded in registry.</span>"
                        return

                self._shell.add_widget(name, title)
                _btn.name = "✓ Added"
                _btn.button_type = "success"
                _btn.disabled = True
                promote_btn.visible = True
                self._status.object = f"<span style='color:green'>Added <strong>{title}</strong> to layout.</span>"
            except Exception as exc:
                log.warning("WidgetPicker: failed to add %r: %s", name, exc)
                self._status.object = f"<span style='color:red'>Failed: {exc}</span>"

        def _on_promote(_evt: Any) -> None:
            dialog = PromoteDialog(
                widget_name=name,
                registry=self._registry,
                settings=self._settings,
            )
            self._dialog_area.objects = [dialog.get_panel()]

        add_btn.on_click(_on_add)
        promote_btn.on_click(_on_promote)

        buttons = pn.Row(promote_btn, add_btn, align="center", margin=0)

        return pn.Row(
            info_html,
            pn.layout.HSpacer(),
            buttons,
            sizing_mode="stretch_width",
            css_classes=["wp-card"],
            margin=(0, 0, 4, 0),
        )

    def _build_section(self, title: str, cards: list[pn.viewable.Viewable]) -> pn.viewable.Viewable:
        """Build a collapsible category section."""
        header = pn.pane.HTML(
            f"<div style='font-size:13px;font-weight:600;color:#555;padding:6px 0 4px 2px;"
            f"border-bottom:1px solid #eee;margin-bottom:4px'>{title}</div>",
            sizing_mode="stretch_width",
        )
        return pn.Column(header, *cards, sizing_mode="stretch_width", margin=(0, 0, 8, 0))

    def refresh(self) -> None:
        """Rebuild the widget list from current examples and manifest."""
        self._dialog_area.objects = []
        self._status.object = ""
        if self._list_col is not None:
            self._list_col.objects = list(self._build_list())

    def _build_list(self) -> list[pn.viewable.Viewable]:
        """Build all sections from examples + manifest."""
        examples = _scan_examples(self._examples_dir)
        manifest_entries = self._load_manifest_entries()

        example_names = {e["name"] for e in examples}
        extra_generated = [e for e in manifest_entries if e.get("name") not in example_names]

        categories: dict[str, list[pn.viewable.Viewable]] = {}
        for entry in examples:
            cat = entry.get("category", "Other")
            card = self._build_card(entry, source="example")
            categories.setdefault(cat, []).append(card)

        if extra_generated:
            for entry in extra_generated:
                cat = entry.get("category", "Generated")
                card = self._build_card(entry, source="generated")
                categories.setdefault(cat, []).append(card)

        if not categories:
            return [
                pn.pane.Markdown(
                    "_No widgets available. Ask the chat assistant to create one!_",
                    styles={"color": "#888", "padding": "16px"},
                )
            ]

        sections: list[pn.viewable.Viewable] = []
        for cat_name in sorted(categories):
            sections.append(self._build_section(cat_name, categories[cat_name]))
        return sections

    def get_panel(self) -> pn.viewable.Viewable:
        """Return the full WidgetPicker Panel component."""
        items = self._build_list()
        self._list_col = pn.Column(
            *items,
            sizing_mode="stretch_width",
            styles={"overflow-y": "auto", "max-height": "calc(100vh - 160px)"},
        )

        refresh_btn = pn.widgets.Button(
            name="↻ Refresh",
            button_type="light",
            width=80,
            height=28,
        )
        refresh_btn.on_click(lambda _: self.refresh())

        header = pn.Row(
            pn.pane.HTML(
                "<h3 style='margin:0;font-family:system-ui,sans-serif;color:#333'>"
                "Widget Library</h3>",
            ),
            pn.layout.HSpacer(),
            refresh_btn,
            sizing_mode="stretch_width",
            styles={"align-items": "center", "padding": "4px 0 8px 0"},
        )

        return pn.Column(
            pn.pane.HTML(f"<style>{_CARD_CSS}</style>", height=0, margin=0),
            header,
            self._status,
            self._list_col,
            self._dialog_area,
            sizing_mode="stretch_both",
            styles=_CONTAINER_STYLES,
        )
