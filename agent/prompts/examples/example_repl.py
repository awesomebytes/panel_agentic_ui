"""{
  "name": "repl",
  "version": 1,
  "title": "Python REPL",
  "description": "Interactive Python REPL with controlled execution context",
  "tags": ["repl", "python", "code", "interactive"],
  "category": "REPL"
}"""
from __future__ import annotations

import io
import sys
import traceback

import panel as pn
import param


class PythonREPL(param.Parameterized):
    output_text = param.String(default="")
    error_text = param.String(default="")

    def __init__(self, **params):
        super().__init__(**params)
        self._exec_globals: dict = {}

    def _run_code(self, source: str) -> None:
        stdout_capture = io.StringIO()
        old_stdout = sys.stdout
        self.error_text = ""
        try:
            sys.stdout = stdout_capture
            exec(source, self._exec_globals)  # noqa: S102
            self.output_text = stdout_capture.getvalue()
        except Exception:
            self.output_text = stdout_capture.getvalue()
            self.error_text = traceback.format_exc()
        finally:
            sys.stdout = old_stdout

    def _on_run(self, event) -> None:
        source = self._code_input.value
        if source.strip():
            self._run_code(source)

    def get_panel(self) -> pn.Column:
        self._code_input = pn.widgets.TextAreaInput(
            name="",
            placeholder="print('Hello, world!')",
            height=180,
            width=500,
        )

        run_btn = pn.widgets.Button(name="Run", button_type="primary", width=80)
        run_btn.on_click(self._on_run)

        clear_btn = pn.widgets.Button(name="Clear", button_type="light", width=80)
        clear_btn.on_click(lambda e: (
            setattr(self, "output_text", ""),
            setattr(self, "error_text", ""),
        ))

        output_pane = pn.pane.Markdown(
            object=self.param.output_text,
            styles={
                "background": "#f5f5f5",
                "padding": "8px",
                "border-radius": "4px",
                "font-family": "monospace",
                "white-space": "pre-wrap",
                "min-height": "60px",
            },
        )
        error_pane = pn.pane.Markdown(
            object=self.param.error_text,
            styles={
                "background": "#fff0f0",
                "padding": "8px",
                "border-radius": "4px",
                "font-family": "monospace",
                "white-space": "pre-wrap",
                "color": "#c00",
            },
        )

        return pn.Column(
            pn.pane.Markdown("## Python REPL", styles={"color": "#222"}),
            self._code_input,
            pn.Row(run_btn, clear_btn),
            pn.pane.Markdown("**Output:**", styles={"margin-top": "8px"}),
            output_pane,
            pn.bind(lambda e: error_pane if e else pn.pane.Markdown(""), self.param.error_text),
            styles={"background": "#ffffff", "padding": "16px"},
        )


def build() -> pn.Column:
    return PythonREPL().get_panel()
