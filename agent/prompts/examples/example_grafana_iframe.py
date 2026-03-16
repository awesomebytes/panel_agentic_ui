"""{
  "name": "grafana_iframe",
  "version": 1,
  "title": "Grafana Dashboard",
  "description": "Embedded Grafana dashboard",
  "tags": ["grafana", "dashboard", "monitoring", "iframe"],
  "category": "Monitoring"
}"""
from __future__ import annotations

import panel as pn
import param

_SETUP_HTML = """
<div style="background:#1a1a2e;color:#ccc;font-family:sans-serif;
            padding:40px;border-radius:6px;text-align:center;min-height:300px;
            display:flex;flex-direction:column;align-items:center;justify-content:center;">
  <div style="font-size:48px;margin-bottom:16px;">&#128202;</div>
  <div style="font-size:18px;font-weight:bold;color:#fff;margin-bottom:8px;">
    Grafana not configured
  </div>
  <div style="font-size:13px;line-height:1.8;max-width:420px;">
    Enter your Grafana dashboard URL above and click <strong>Load</strong>.<br/>
    Example:<br/>
    <code style="background:#333;padding:2px 6px;border-radius:3px;">
      http://grafana:3000/d/abc123/my-dashboard?orgId=1&kiosk
    </code>
  </div>
  <div style="margin-top:16px;">
    <a href="https://grafana.com/docs/grafana/latest/sharing/share-dashboard/"
       target="_blank"
       style="color:#7eb5f7;font-size:12px;">
      How to get a Grafana dashboard URL &#8599;
    </a>
  </div>
</div>
"""

_IFRAME_TEMPLATE = """
<iframe
  src="{url}"
  width="100%"
  height="{height}px"
  frameborder="0"
  style="border-radius:4px;display:block;"
  allowfullscreen
></iframe>
"""


class GrafanaDashboard(param.Parameterized):
    grafana_url = param.String(default="", label="Grafana Dashboard URL")
    height = param.Integer(default=600, bounds=(200, 2000), label="Height (px)")

    def __init__(self, **params):
        super().__init__(**params)
        self._iframe_pane = pn.pane.HTML(
            _SETUP_HTML, sizing_mode="stretch_width", min_height=300
        )

    @param.depends("grafana_url", "height", watch=True)
    def _update_iframe(self) -> None:
        url = self.grafana_url.strip()
        if not url:
            self._iframe_pane.object = _SETUP_HTML
        else:
            self._iframe_pane.object = _IFRAME_TEMPLATE.format(
                url=url, height=self.height
            )

    def _on_load(self, event=None) -> None:
        self._update_iframe()

    def get_panel(self) -> pn.Column:
        url_input = pn.widgets.TextInput.from_param(
            self.param.grafana_url,
            width=480,
            placeholder="http://grafana:3000/d/abc123/dashboard?kiosk",
        )
        height_input = pn.widgets.IntSlider.from_param(
            self.param.height, width=200, start=200, end=2000, step=50
        )
        load_btn = pn.widgets.Button(name="Load", button_type="primary", width=100)
        load_btn.on_click(self._on_load)

        return pn.Column(
            pn.pane.Markdown("## Grafana Dashboard"),
            pn.Row(url_input, load_btn, align="end"),
            pn.Row(pn.pane.Markdown("**Height:**"), height_input),
            self._iframe_pane,
            styles={"background": "#1a1a2e", "padding": "16px", "border-radius": "6px"},
        )


def build() -> pn.viewable.Viewable:
    return GrafanaDashboard().get_panel()
