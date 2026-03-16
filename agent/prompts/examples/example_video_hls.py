"""{
  "name": "video_hls",
  "version": 1,
  "title": "HLS Video Player",
  "description": "HLS video stream player",
  "tags": ["video", "hls", "stream", "camera", "rtsp"],
  "category": "Video"
}"""
from __future__ import annotations

import panel as pn
import param

_PLACEHOLDER_HTML = """
<div style="background:#111;color:#aaa;font-family:sans-serif;
            padding:32px;border-radius:6px;text-align:center;">
  <div style="font-size:48px;margin-bottom:12px;">&#9654;</div>
  <div style="font-size:16px;font-weight:bold;margin-bottom:8px;color:#fff;">
    No HLS Stream Configured
  </div>
  <div style="font-size:13px;line-height:1.6;">
    Enter an HLS URL above and click <strong>Load</strong>.<br/>
    Example: <code>http://host/stream.m3u8</code>
  </div>
</div>
"""

_PLAYER_TEMPLATE = """
<video id="hls-player-{uid}" controls autoplay muted
       style="width:100%;border-radius:6px;background:#000;max-height:480px;">
  Your browser does not support HTML5 video.
</video>
<script>
(function() {{
  var video = document.getElementById('hls-player-{uid}');
  var src = '{url}';
  if (Hls && Hls.isSupported()) {{
    var hls = new Hls();
    hls.loadSource(src);
    hls.attachMedia(video);
  }} else if (video.canPlayType('application/vnd.apple.mpegurl')) {{
    video.src = src;
  }} else {{
    video.insertAdjacentHTML('afterend',
      '<p style="color:red">HLS not supported in this browser.</p>');
  }}
}})();
</script>
"""

_HLS_JS_INCLUDE = """
<script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
"""


class HLSVideoPlayer(param.Parameterized):
    hls_url = param.String(default="", label="HLS URL (.m3u8)")
    _uid: int = 0

    def __init__(self, **params):
        super().__init__(**params)
        HLSVideoPlayer._uid += 1
        self._player_uid = HLSVideoPlayer._uid
        self._video_pane = pn.pane.HTML(
            _PLACEHOLDER_HTML, sizing_mode="stretch_width", min_height=240
        )

    def _load_stream(self, event=None) -> None:
        url = self.hls_url.strip()
        if not url:
            self._video_pane.object = _PLACEHOLDER_HTML
            return
        html = _HLS_JS_INCLUDE + _PLAYER_TEMPLATE.format(
            url=url, uid=self._player_uid
        )
        self._video_pane.object = html

    def get_panel(self) -> pn.Column:
        url_input = pn.widgets.TextInput.from_param(
            self.param.hls_url, width=400, placeholder="http://host/stream.m3u8"
        )
        load_btn = pn.widgets.Button(name="Load", button_type="primary", width=100)
        load_btn.on_click(self._load_stream)

        return pn.Column(
            pn.pane.Markdown("## HLS Video Player"),
            pn.Row(url_input, load_btn, align="end"),
            self._video_pane,
            styles={"background": "#111", "padding": "16px", "border-radius": "6px"},
        )


def build() -> pn.viewable.Viewable:
    return HLSVideoPlayer().get_panel()
