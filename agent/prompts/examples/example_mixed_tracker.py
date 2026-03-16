"""{
  "name": "mixed_tracker",
  "version": 1,
  "title": "System Tracker",
  "description": "Real-time CPU and memory tracking with start/stop",
  "tags": ["tracker", "cpu", "memory", "mixed", "real-time"],
  "category": "Mixed"
}"""
from __future__ import annotations

import asyncio

import httpx
import panel as pn
import param


class MixedTracker(param.Parameterized):
    cpu_text = param.String(default="CPU: —")
    mem_text = param.String(default="Memory: —")
    running = param.Boolean(default=False)

    def __init__(self, **params):
        super().__init__(**params)
        self._callback = None

    def _on_start(self, event) -> None:
        if self._callback is not None:
            return
        self.running = True
        self._callback = pn.state.add_periodic_callback(self._poll, period=2000)

    def _on_stop(self, event) -> None:
        if self._callback is not None:
            self._callback.stop()
            self._callback = None
        self.running = False
        self.cpu_text = "CPU: —"
        self.mem_text = "Memory: —"

    def _poll(self) -> None:
        asyncio.ensure_future(self._fetch_metrics())

    async def _fetch_metrics(self) -> None:
        try:
            async with httpx.AsyncClient() as client:
                cpu_resp, mem_resp = await asyncio.gather(
                    client.get("http://localhost:8001/telemetry/cpu", timeout=3.0),
                    client.get("http://localhost:8001/telemetry/memory", timeout=3.0),
                )
            if cpu_resp.status_code == 200:
                data = cpu_resp.json()
                load = data.get("load", "?")
                self.cpu_text = f"CPU: {load}%"
            if mem_resp.status_code == 200:
                data = mem_resp.json()
                pct = data.get("percent", "?")
                self.mem_text = f"Memory: {pct}%"
        except Exception as exc:
            self.cpu_text = f"Error: {exc}"

    def get_panel(self) -> pn.Column:
        start_btn = pn.widgets.Button(name="Start", button_type="success", width=100)
        stop_btn = pn.widgets.Button(name="Stop", button_type="danger", width=100)
        start_btn.on_click(self._on_start)
        stop_btn.on_click(self._on_stop)

        cpu_pane = pn.pane.Markdown(
            object=self.param.cpu_text,
            styles={"background": "#f0f4ff", "padding": "8px", "border-radius": "4px", "font-size": "1.1em"},
        )
        mem_pane = pn.pane.Markdown(
            object=self.param.mem_text,
            styles={"background": "#f0fff4", "padding": "8px", "border-radius": "4px", "font-size": "1.1em"},
        )

        return pn.Column(
            pn.pane.Markdown("## System Tracker", styles={"color": "#222"}),
            pn.Row(start_btn, stop_btn),
            cpu_pane,
            mem_pane,
            styles={"background": "#ffffff", "padding": "16px"},
        )


def build() -> pn.Column:
    return MixedTracker().get_panel()
