"""{
  "name": "plot_oneoff",
  "version": 1,
  "title": "System Snapshot",
  "description": "One-time system stats snapshot",
  "tags": ["plot", "system", "memory", "disk", "snapshot"],
  "category": "Plot"
}"""
from __future__ import annotations

import asyncio

import httpx
import panel as pn
import param
from bokeh.models import ColumnDataSource, FactorRange
from bokeh.plotting import figure
from bokeh.transform import factor_cmap


MEMORY_URL = "http://localhost:8001/telemetry/memory"
DISK_URL = "http://localhost:8001/telemetry/disk"

PALETTE = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"]


class SystemSnapshot(param.Parameterized):
    status = param.String(default="Loading...")

    def __init__(self, **params):
        super().__init__(**params)
        self._plot_pane = pn.pane.Bokeh(sizing_mode="stretch_width")
        pn.state.execute(self._load)

    async def _load(self) -> None:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                mem_resp, disk_resp = await asyncio.gather(
                    client.get(MEMORY_URL),
                    client.get(DISK_URL),
                )
                mem_resp.raise_for_status()
                disk_resp.raise_for_status()
                mem = mem_resp.json()
                disk = disk_resp.json()

            categories = ["Memory Used", "Memory Free", "Disk Used", "Disk Free"]
            mem_used_gb = mem["used"] / 1024**3
            mem_free_gb = (mem["total"] - mem["used"]) / 1024**3
            disk_used_gb = disk["used"] / 1024**3
            disk_free_gb = (disk["total"] - disk["used"]) / 1024**3
            values = [mem_used_gb, mem_free_gb, disk_used_gb, disk_free_gb]

            source = ColumnDataSource(dict(cats=categories, vals=values))
            fig = figure(
                x_range=FactorRange(*categories),
                height=300,
                sizing_mode="stretch_width",
                toolbar_location=None,
                background_fill_color="#ffffff",
                border_fill_color="#ffffff",
                title="Memory & Disk (GB)",
            )
            fig.vbar(
                x="cats",
                top="vals",
                width=0.6,
                source=source,
                fill_color=factor_cmap("cats", palette=PALETTE, factors=categories),
                line_color=None,
            )
            fig.yaxis.axis_label = "GB"
            fig.xaxis.major_label_orientation = 0.4
            self._plot_pane.object = fig
            self.status = (
                f"Memory: {mem['percent']:.1f}% used  |  "
                f"Disk: {disk['percent']:.1f}% used"
            )
        except Exception as exc:
            self.status = f"Failed to load data: {exc}"

    def get_panel(self) -> pn.Column:
        status_pane = pn.pane.Markdown(
            object=self.param.status,
            styles={"color": "#555", "font-size": "13px"},
        )
        return pn.Column(
            pn.pane.Markdown("## System Snapshot", styles={"color": "#222"}),
            status_pane,
            self._plot_pane,
            styles={"background": "#ffffff", "padding": "16px"},
        )


def build() -> pn.Column:
    return SystemSnapshot().get_panel()
