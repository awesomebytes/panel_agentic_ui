"""{
  "name": "slider_control",
  "version": 1,
  "title": "Slider Command",
  "description": "Slider that sends commands to the backend",
  "tags": ["slider", "control", "command", "action"],
  "category": "Control"
}"""
from __future__ import annotations

import asyncio

import httpx
import panel as pn
import param


class SliderControl(param.Parameterized):
    speed = param.Number(default=0, bounds=(0, 100))
    status_text = param.String(default="Adjust the slider to set speed.")

    def _on_slider_change(self, event) -> None:
        asyncio.ensure_future(self._send_command(event.new))

    async def _send_command(self, value: float) -> None:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "http://localhost:8002/command/set_speed",
                    json={"params": {"speed": value}},
                    timeout=5.0,
                )
            if resp.status_code == 200:
                self.status_text = f"Command sent: speed={value:.0f}"
            else:
                self.status_text = f"Error {resp.status_code}: {resp.text[:80]}"
        except Exception as exc:
            self.status_text = f"Request failed: {exc}"

    def get_panel(self) -> pn.Column:
        slider = pn.widgets.IntSlider(
            name="Speed",
            start=0,
            end=100,
            value=0,
            step=1,
            width=300,
        )
        slider.param.watch(self._on_slider_change, "value")

        status = pn.pane.Markdown(
            object=self.param.status_text,
            styles={"background": "#f5f5f5", "padding": "8px", "border-radius": "4px"},
        )

        return pn.Column(
            pn.pane.Markdown("## Slider Command", styles={"color": "#222"}),
            slider,
            status,
            styles={"background": "#ffffff", "padding": "16px"},
        )


def build() -> pn.Column:
    return SliderControl().get_panel()
