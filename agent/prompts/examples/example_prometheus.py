"""{
  "name": "prometheus",
  "version": 1,
  "title": "Prometheus Query",
  "description": "Execute PromQL queries",
  "tags": ["prometheus", "metrics", "monitoring", "promql"],
  "category": "Monitoring"
}"""
from __future__ import annotations

import json

import panel as pn
import param

PROMETHEUS_URL = "http://localhost:8004/metrics/query"


class PrometheusQuery(param.Parameterized):
    query = param.String(default="up", label="PromQL Query")
    result_text = param.String(default="Run a query to see results.")
    running = param.Boolean(default=False)

    async def _execute_query(self) -> None:
        self.running = True
        self.result_text = "Querying…"
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(PROMETHEUS_URL, params={"query": self.query})
                resp.raise_for_status()
                data = resp.json()
            self.result_text = json.dumps(data, indent=2)
        except Exception as exc:
            err = str(exc)
            if "Connection" in err or "refused" in err.lower():
                self.result_text = (
                    "Prometheus not configured.\n"
                    f"Endpoint: {PROMETHEUS_URL}\n"
                    "Start the metrics backend or update PROMETHEUS_URL."
                )
            else:
                self.result_text = f"Query error: {err}"
        finally:
            self.running = False

    def _on_run(self, event) -> None:
        pn.state.execute(self._execute_query)

    def get_panel(self) -> pn.Column:
        query_input = pn.widgets.TextInput.from_param(
            self.param.query, width=400, placeholder="e.g. up, rate(http_requests_total[5m])"
        )
        run_btn = pn.widgets.Button(name="Run Query", button_type="primary", width=120)
        run_btn.on_click(self._on_run)

        result_pane = pn.pane.Str(
            object=self.param.result_text,
            styles={
                "background": "#1e1e1e",
                "color": "#d4d4d4",
                "padding": "12px",
                "border-radius": "4px",
                "font-family": "monospace",
                "white-space": "pre-wrap",
                "min-height": "120px",
                "font-size": "12px",
            },
            sizing_mode="stretch_width",
        )

        return pn.Column(
            pn.pane.Markdown("## Prometheus Query"),
            pn.Row(query_input, run_btn, align="end"),
            result_pane,
            styles={"background": "#ffffff", "padding": "16px"},
        )


def build() -> pn.viewable.Viewable:
    return PrometheusQuery().get_panel()
