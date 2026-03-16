"""Promote widget to GitHub PR — Panel dialog card."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import panel as pn
import param

from agent.pr_creator import GitHubPRCreator
from config import Settings

log = logging.getLogger(__name__)

_CARD_STYLES = {
    "background": "#ffffff",
    "border": "1px solid #d0d8e4",
    "border-radius": "8px",
    "box-shadow": "0 4px 16px rgba(0,0,0,0.10)",
}


class PromoteDialog(param.Parameterized):
    """Panel card form for promoting a generated widget file to a GitHub PR.

    Usage
    -----
    dialog = PromoteDialog("cpu_monitor", registry, settings)
    panel.objects = [dialog.get_panel()]
    """

    visible = param.Boolean(default=False)

    def __init__(
        self,
        widget_name: str,
        registry: Any,
        settings: Settings,
        widget_path: Path | str | None = None,
        chat_log: str = "",
        **params: Any,
    ) -> None:
        super().__init__(**params)
        self._widget_name = widget_name
        self._registry = registry
        self._settings = settings
        self._widget_path = Path(widget_path) if widget_path else None
        self._chat_log = chat_log
        self._panel = self._build()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_widget_path(self) -> Path:
        """Return the most recent versioned .py file for the widget."""
        if self._widget_path and Path(self._widget_path).exists():
            return Path(self._widget_path)
        widgets_dir = Path(self._settings.widgets_dir)
        candidates = sorted(
            widgets_dir.glob(f"widget_{self._widget_name}_v*.py"),
            key=lambda p: p.name,
            reverse=True,
        )
        if not candidates:
            raise FileNotFoundError(
                f"No widget file found for {self._widget_name!r} in {widgets_dir}"
            )
        return candidates[0]

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self) -> pn.viewable.Viewable:
        configured = GitHubPRCreator.is_configured(self._settings)

        name_display = pn.widgets.TextInput(
            name="Widget",
            value=self._widget_name,
            disabled=True,
            sizing_mode="stretch_width",
        )
        description = pn.widgets.TextAreaInput(
            name="Description",
            placeholder="Describe what this widget does and why it is useful…",
            height=90,
            sizing_mode="stretch_width",
        )
        branch_input = pn.widgets.TextInput(
            name="Branch",
            value=f"widget/{self._widget_name}",
            sizing_mode="stretch_width",
        )
        include_example = pn.widgets.Checkbox(
            name="Include as few-shot example",
            value=False,
        )

        initial_status = (
            ""
            if configured
            else (
                "⚠ GitHub not configured — set `MONITOR_GITHUB_TOKEN` and "
                "`MONITOR_GITHUB_REPO` (format: `owner/repo`)."
            )
        )
        status = pn.pane.Markdown(
            initial_status,
            sizing_mode="stretch_width",
            stylesheets=["p { font-size: 13px; margin: 4px 0; }"],
        )

        create_btn = pn.widgets.Button(
            name="Create PR",
            button_type="primary",
            disabled=not configured,
            sizing_mode="stretch_width",
        )
        cancel_btn = pn.widgets.Button(
            name="Cancel",
            button_type="light",
            sizing_mode="stretch_width",
        )

        def _on_cancel(_: Any) -> None:
            self.visible = False

        cancel_btn.on_click(_on_cancel)

        async def _do_create() -> None:
            create_btn.disabled = True
            status.object = "⏳ Creating PR…"
            try:
                creator = GitHubPRCreator(self._settings)
                widget_path = self._resolve_widget_path()
                pr_url = await creator.create_pr(
                    widget_name=self._widget_name,
                    widget_path=widget_path,
                    description=description.value or f"Widget: {self._widget_name}",
                    chat_log=self._chat_log,
                    include_as_example=include_example.value,
                )
                status.object = f"✓ PR created: [{pr_url}]({pr_url})"
                create_btn.name = "PR Created"
            except Exception as exc:
                log.exception(
                    "PromoteDialog: PR creation failed for %r", self._widget_name
                )
                status.object = f"✗ Error: {exc}"
                create_btn.disabled = False

        def _on_create(_: Any) -> None:
            asyncio.ensure_future(_do_create())

        create_btn.on_click(_on_create)

        return pn.Card(
            name_display,
            description,
            branch_input,
            include_example,
            status,
            pn.Row(cancel_btn, create_btn, sizing_mode="stretch_width"),
            title=f"Promote — {self._widget_name}",
            collapsible=False,
            sizing_mode="stretch_width",
            styles=_CARD_STYLES,
            header_background="#f0f4f8",
        )

    def get_panel(self) -> pn.viewable.Viewable:
        return self._panel
