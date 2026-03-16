"""{
  "name": "audit_viewer",
  "version": 1,
  "title": "Audit Log Viewer",
  "description": "Auto-refreshing tabular view of the audit log",
  "tags": ["audit", "log", "table", "monitoring", "history"],
  "category": "Audit"
}"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx
import pandas as pd
import panel as pn
import param

AUDIT_URL = "http://localhost:8005/audit/recent"
LIMIT = 50
POLL_INTERVAL_MS = 5000


class AuditViewer(param.Parameterized):
    _status = param.String(default="")
    _cb = param.Parameter(default=None)

    def __init__(self, **params):
        super().__init__(**params)
        self._tabulator = pn.widgets.Tabulator(
            pd.DataFrame(columns=["timestamp", "action", "user", "details"]),
            show_index=False,
            sizing_mode="stretch_width",
            height=400,
            theme="simple",
            disabled=True,
            header_filters=False,
        )

    @staticmethod
    def _format_ts(ts: float) -> str:
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    async def _fetch(self) -> None:
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                resp = await client.get(AUDIT_URL, params={"limit": LIMIT})
                resp.raise_for_status()
                rows = resp.json()
            df = pd.DataFrame(
                [
                    {
                        "timestamp": self._format_ts(r["ts"]),
                        "action": r.get("action", ""),
                        "user": r.get("user", ""),
                        "details": str(r.get("details", "")),
                    }
                    for r in rows
                ],
                columns=["timestamp", "action", "user", "details"],
            )
            self._tabulator.value = df
            self._status = f"Last updated: {datetime.now().strftime('%H:%M:%S')}"
        except Exception as exc:
            self._status = f"Fetch error: {exc}"

    def _poll(self) -> None:
        asyncio.ensure_future(self._fetch())

    def _start(self) -> None:
        self._poll()
        self._cb = pn.state.add_periodic_callback(self._poll, period=POLL_INTERVAL_MS)

    def _stop(self) -> None:
        if self._cb is not None:
            try:
                self._cb.stop()
            except Exception:
                pass
            self._cb = None

    def get_panel(self) -> pn.Column:
        self._start()

        status_pane = pn.pane.Markdown(
            object=self.param._status,
            styles={"color": "#666", "font-size": "0.85em", "margin": "0"},
        )

        col = pn.Column(
            pn.pane.Markdown("## Audit Log Viewer", styles={"color": "#222"}),
            self._tabulator,
            status_pane,
            styles={"background": "#ffffff", "padding": "16px"},
            sizing_mode="stretch_width",
        )

        def _on_destroy(*_args):
            self._stop()

        col.param.watch(_on_destroy, "objects")
        return col


def build() -> pn.Column:
    return AuditViewer().get_panel()
