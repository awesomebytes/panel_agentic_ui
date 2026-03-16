"""{
  "name": "camera_overlay",
  "version": 1,
  "title": "Camera Overlay",
  "description": "Camera feed with detection overlay",
  "tags": ["camera", "video", "detection", "overlay", "vision"],
  "category": "Camera"
}"""
from __future__ import annotations

import base64
import io
from pathlib import Path

import panel as pn
import param

FIXTURE_PATH = Path(__file__).parent.parent.parent.parent / "tests" / "fixtures" / "test_frame.jpg"
POLL_INTERVAL_MS = 1000


def _placeholder_b64() -> str:
    """Return a base64-encoded minimal PNG placeholder (1x1 blue pixel)."""
    _PNG_1X1_BLUE = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
        b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    return base64.b64encode(_PNG_1X1_BLUE).decode()


def _load_fixture_b64() -> str | None:
    try:
        if FIXTURE_PATH.exists():
            return base64.b64encode(FIXTURE_PATH.read_bytes()).decode()
    except Exception:
        pass
    return None


class CameraOverlay(param.Parameterized):
    rtsp_url = param.String(default="", label="RTSP URL")
    overlay_text = param.String(default="No detections", label="Overlay Text")
    status = param.String(default="Using static frame")
    _cb = param.Parameter(default=None)

    def __init__(self, **params):
        super().__init__(**params)
        fixture = _load_fixture_b64()
        self._static_b64 = fixture if fixture else _placeholder_b64()
        self._img_ext = "jpeg" if fixture else "png"
        self._frame_pane = pn.pane.HTML(self._make_html(), sizing_mode="stretch_width")

    def _make_html(self) -> str:
        b64 = self._static_b64
        ext = self._img_ext
        overlay = self.overlay_text or ""
        return f"""
<div style="position:relative;display:inline-block;width:100%;">
  <img src="data:image/{ext};base64,{b64}"
       style="width:100%;border-radius:4px;display:block;" />
  <div style="position:absolute;top:8px;left:8px;background:rgba(0,0,0,0.6);
              color:#0f0;font-family:monospace;font-size:13px;padding:4px 8px;
              border-radius:3px;">{overlay}</div>
</div>
"""

    async def _refresh_frame(self) -> None:
        if not self.rtsp_url:
            return
        try:
            import httpx
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(self.rtsp_url)
                resp.raise_for_status()
                self._static_b64 = base64.b64encode(resp.content).decode()
                self._img_ext = "jpeg"
        except Exception as exc:
            self.status = f"Feed error: {exc}"
        self._frame_pane.object = self._make_html()

    @param.depends("overlay_text", watch=True)
    def _on_overlay_change(self):
        self._frame_pane.object = self._make_html()

    def get_panel(self) -> pn.Column:
        url_input = pn.widgets.TextInput.from_param(self.param.rtsp_url, width=320,
                                                    placeholder="rtsp://host:554/stream")
        overlay_input = pn.widgets.TextInput.from_param(self.param.overlay_text, width=320)
        status_pane = pn.pane.Str(object=self.param.status,
                                  styles={"color": "#555", "font-size": "12px"})

        def _on_connect(event):
            self.status = f"Connecting to {self.rtsp_url}" if self.rtsp_url else "No URL set"
            if self._cb is None and self.rtsp_url:
                self._cb = pn.state.add_periodic_callback(self._refresh_frame, POLL_INTERVAL_MS)

        btn = pn.widgets.Button(name="Connect", button_type="primary", width=120)
        btn.on_click(_on_connect)

        col = pn.Column(
            pn.pane.Markdown("## Camera Overlay"),
            pn.Row(url_input, btn),
            overlay_input,
            status_pane,
            self._frame_pane,
            styles={"background": "#ffffff", "padding": "16px"},
        )

        def _on_destroy(*_):
            if self._cb is not None:
                try:
                    self._cb.stop()
                except Exception:
                    pass

        col.param.watch(_on_destroy, "objects")
        return col


def build() -> pn.viewable.Viewable:
    return CameraOverlay().get_panel()
