"""{
  "name": "plot_ros",
  "version": 1,
  "title": "ROS 2 Topic Plot",
  "description": "Plots ROS 2 topic data",
  "tags": ["ros", "ros2", "plot", "topic", "robot"],
  "category": "ROS"
}"""
from __future__ import annotations

from collections import deque
from datetime import datetime

import panel as pn
import param

try:
    import rclpy
    from rclpy.node import Node
    _ROS_AVAILABLE = True
except ImportError:
    _ROS_AVAILABLE = False

MAX_POINTS = 60
POLL_INTERVAL_MS = 500


class ROSTopicPlot(param.Parameterized):
    topic = param.String(default="/chatter", label="Topic")
    status = param.String(default="")
    _cb = param.Parameter(default=None)

    def __init__(self, **params):
        super().__init__(**params)
        self._times: deque = deque(maxlen=MAX_POINTS)
        self._values: deque = deque(maxlen=MAX_POINTS)
        self._node = None
        self._executor = None
        self._fig = None
        self._source = None
        if _ROS_AVAILABLE:
            self._fig = self._make_figure()
            self._source = self._fig.renderers[0].data_source

    def _make_figure(self):
        from bokeh.models import DatetimeTickFormatter
        from bokeh.plotting import figure
        fig = figure(
            title="ROS 2 Topic Data",
            x_axis_type="datetime",
            height=300,
            sizing_mode="stretch_width",
            toolbar_location=None,
        )
        fig.xaxis.formatter = DatetimeTickFormatter(seconds="%H:%M:%S")
        fig.yaxis.axis_label = "Value"
        fig.line(x="x", y="y", line_width=2, color="#e74c3c", source={"x": [], "y": []})
        return fig

    def _init_ros(self) -> bool:
        try:
            if not rclpy.ok():
                rclpy.init()
            import threading

            class _Listener(Node):
                def __init__(self_node):
                    super().__init__("panel_topic_plotter")
                    self_node.latest = None
                    self_node.create_subscription(
                        __import__("std_msgs.msg", fromlist=["Float64"]).Float64,
                        self.topic,
                        lambda msg: setattr(self_node, "latest", msg.data),
                        10,
                    )

            self._node = _Listener()
            import rclpy.executors
            self._executor = rclpy.executors.SingleThreadedExecutor()
            self._executor.add_node(self._node)
            t = threading.Thread(target=self._executor.spin, daemon=True)
            t.start()
            return True
        except Exception as exc:
            self.status = f"ROS init error: {exc}"
            return False

    async def _poll(self) -> None:
        if self._node is None:
            return
        try:
            val = self._node.latest
            if val is not None:
                self._times.append(datetime.now())
                self._values.append(float(val))
                self._source.data = {"x": list(self._times), "y": list(self._values)}
                self.status = f"Last value: {val:.4f}"
        except Exception as exc:
            self.status = f"Poll error: {exc}"

    def get_panel(self) -> pn.Column:
        if not _ROS_AVAILABLE:
            return pn.Column(
                pn.pane.Markdown("## ROS 2 Topic Plot"),
                pn.pane.Alert(
                    "**ROS 2 not available.** Install rclpy and source your ROS 2 workspace.",
                    alert_type="warning",
                ),
                styles={"background": "#ffffff", "padding": "16px"},
            )

        topic_input = pn.widgets.TextInput.from_param(self.param.topic, width=300)
        status_pane = pn.pane.Str(object=self.param.status, styles={"color": "#555", "font-size": "12px"})
        plot_pane = pn.pane.Bokeh(self._fig, sizing_mode="stretch_width")

        def _on_connect(event):
            self._init_ros()
            self._cb = pn.state.add_periodic_callback(self._poll, period=POLL_INTERVAL_MS)

        btn = pn.widgets.Button(name="Connect", button_type="primary", width=120)
        btn.on_click(_on_connect)

        col = pn.Column(
            pn.pane.Markdown("## ROS 2 Topic Plot"),
            pn.Row(topic_input, btn),
            status_pane,
            plot_pane,
            styles={"background": "#ffffff", "padding": "16px"},
        )

        def _on_destroy(*_):
            if self._cb is not None:
                try:
                    self._cb.stop()
                except Exception:
                    pass
            if self._executor is not None:
                try:
                    self._executor.shutdown(wait=False)
                except Exception:
                    pass

        col.param.watch(_on_destroy, "objects")
        return col


def build() -> pn.viewable.Viewable:
    return ROSTopicPlot().get_panel()
