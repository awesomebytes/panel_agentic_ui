"""{
  "name": "button_subprocess",
  "version": 1,
  "title": "Subprocess Runner",
  "description": "Runs async subprocess and shows output",
  "tags": ["button", "subprocess", "async", "command"],
  "category": "Action"
}"""
from __future__ import annotations

import asyncio

import panel as pn
import param


class SubprocessRunner(param.Parameterized):
    output_text = param.String(default="Output will appear here.")
    running = param.Boolean(default=False)

    async def _run_command(self) -> None:
        self.running = True
        self.output_text = "Running..."
        try:
            proc = await asyncio.create_subprocess_exec(
                "uname", "-a",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0:
                self.output_text = stdout.decode().strip()
            else:
                self.output_text = f"Error (exit {proc.returncode}):\n{stderr.decode().strip()}"
        except Exception as exc:
            self.output_text = f"Failed to run command: {exc}"
        finally:
            self.running = False

    def _on_click(self, event) -> None:
        pn.state.execute(self._run_command)

    def get_panel(self) -> pn.Column:
        btn = pn.widgets.Button(
            name="Run uname -a",
            button_type="primary",
            width=200,
        )
        btn.on_click(self._on_click)

        output_pane = pn.pane.Str(
            object=self.param.output_text,
            styles={
                "background": "#1e1e1e",
                "color": "#d4d4d4",
                "padding": "10px",
                "border-radius": "4px",
                "font-family": "monospace",
                "white-space": "pre-wrap",
                "min-height": "60px",
            },
        )

        return pn.Column(
            pn.pane.Markdown("## Subprocess Runner", styles={"color": "#222"}),
            btn,
            output_pane,
            styles={"background": "#ffffff", "padding": "16px"},
        )


def build() -> pn.Column:
    return SubprocessRunner().get_panel()
