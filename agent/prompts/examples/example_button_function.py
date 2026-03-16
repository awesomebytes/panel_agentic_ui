"""{
  "name": "button_function",
  "version": 1,
  "title": "Function Button",
  "description": "Button that calls a Python function",
  "tags": ["button", "action", "function"],
  "category": "Action"
}"""
from __future__ import annotations

import math
import random

import panel as pn
import param


class FunctionButton(param.Parameterized):
    result_text = param.String(default="Click the button to run a computation.")

    def _on_click(self, event) -> None:
        n = random.randint(5, 12)
        result = math.factorial(n)
        self.result_text = f"factorial({n}) = {result:,}"

    def get_panel(self) -> pn.Column:
        btn = pn.widgets.Button(
            name="Run Computation",
            button_type="primary",
            width=200,
        )
        btn.on_click(self._on_click)

        result_pane = pn.pane.Markdown(
            object=self.param.result_text,
            styles={"background": "#f5f5f5", "padding": "8px", "border-radius": "4px"},
        )

        return pn.Column(
            pn.pane.Markdown("## Function Button", styles={"color": "#222"}),
            btn,
            result_pane,
            styles={"background": "#ffffff", "padding": "16px"},
        )


def build() -> pn.Column:
    return FunctionButton().get_panel()
