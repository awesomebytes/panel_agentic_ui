"""{
  "name": "plot_streaming",
  "version": 1,
  "title": "Streaming CPU Plot",
  "description": "Real-time CPU usage streaming plot",
  "tags": ["plot", "streaming", "cpu", "telemetry", "real-time"],
  "category": "Plot"
}"""
from __future__ import annotations

from collections import deque
from datetime import datetime

import httpx
import panel as pn
import param
from bokeh.models import DatetimeTickFormatter
from bokeh.plotting import figure


MAX_POINTS = 30
POLL_INTERVAL_MS = 2000
TELEMETRY_CPU_URL = "http://localhost:8001/telemetry/cpu"


class StreamingCPUPlot(param.Parameterized):
    _times: deque = param.Parameter(default=None)
    _values: deque = param.Parameter(default=None)
    _cb = param.Parameter(default=None)

    def __init__(self, **params):
        super().__init__(**params)
        self._times = deque(maxlen=MAX_POINTS)
        self._values = deque(maxlen=MAX_POINTS)
        self._fig = self._make_figure()
        self._source = self._fig.renderers[0].data_source

    def _make_figure(self):
        fig = figure(
            title="CPU Load",
            x_axis_type="datetime",
            height=300,
            sizing_mode="stretch_width",
            background_fill_color="#ffffff",
            border_fill_color="#ffffff",
            toolbar_location=None,
        )
        fig.xaxis.formatter = DatetimeTickFormatter(seconds="%H:%M:%S")
        fig.yaxis.axis_label = "Load (%)"
        fig.line(x="x", y="y", line_width=2, color="#1f77b4", source={"x": [], "y": []})
        return fig

    async def _fetch_and_update(self) -> None:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(TELEMETRY_CPU_URL)
                resp.raise_for_status()
                data = resp.json()
            load = data.get("load", 0.0)
            self._times.append(datetime.now())
            self._values.append(load)
            self._source.data = {
                "x": list(self._times),
                "y": list(self._values),
            }
        except Exception:
            pass

    def _start_polling(self) -> None:
        self._cb = pn.state.add_periodic_callback(
            self._fetch_and_update, period=POLL_INTERVAL_MS
        )

    def _stop_polling(self) -> None:
        if self._cb is not None:
            try:
                self._cb.stop()
            except Exception:
                pass
            self._cb = None

    def get_panel(self) -> pn.Column:
        self._start_polling()
        plot_pane = pn.pane.Bokeh(self._fig, sizing_mode="stretch_width")

        col = pn.Column(
            pn.pane.Markdown("## Streaming CPU Plot", styles={"color": "#222"}),
            plot_pane,
            styles={"background": "#ffffff", "padding": "16px"},
        )

        def _on_destroy(*_args):
            self._stop_polling()

        col.param.watch(_on_destroy, "objects")
        return col


def build() -> pn.Column:
    return StreamingCPUPlot().get_panel()
