"""{
  "name": "notes",
  "version": 1,
  "title": "Notes",
  "description": "Persistent notes editor",
  "tags": ["notes", "editor", "text", "persistence"],
  "category": "Notes"
}"""
from __future__ import annotations

from pathlib import Path

import panel as pn
import param

_NOTES_FILE = Path("notes/default_note.md")


class NotesEditor(param.Parameterized):
    content = param.String(default="")
    status_text = param.String(default="")

    def __init__(self, **params):
        super().__init__(**params)
        self._load()

    def _load(self) -> None:
        if _NOTES_FILE.exists():
            self.content = _NOTES_FILE.read_text(encoding="utf-8")
            self.status_text = "Note loaded."
        else:
            self.status_text = "No saved note found. Start typing!"

    def _on_save(self, event) -> None:
        try:
            _NOTES_FILE.parent.mkdir(parents=True, exist_ok=True)
            _NOTES_FILE.write_text(self.content, encoding="utf-8")
            self.status_text = "Note saved."
        except OSError as exc:
            self.status_text = f"Save failed: {exc}"

    def get_panel(self) -> pn.Column:
        editor = pn.widgets.TextAreaInput(
            name="",
            value=self.content,
            placeholder="Write your notes here…",
            height=300,
            width=500,
        )
        editor.param.watch(lambda e: setattr(self, "content", e.new), "value")

        save_btn = pn.widgets.Button(name="Save", button_type="primary", width=100)
        save_btn.on_click(self._on_save)

        status = pn.pane.Markdown(
            object=self.param.status_text,
            styles={"color": "#555", "font-size": "0.9em"},
        )

        return pn.Column(
            pn.pane.Markdown("## Notes", styles={"color": "#222"}),
            editor,
            pn.Row(save_btn, status),
            styles={"background": "#ffffff", "padding": "16px"},
        )


def build() -> pn.Column:
    return NotesEditor().get_panel()
