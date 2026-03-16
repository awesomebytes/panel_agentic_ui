"""Panel Agentic UI — Entry point.

Works with both:
  pixi run panel serve main.py --port 5006
  pixi run python main.py
"""
from __future__ import annotations

import logging
import sys

import panel as pn

from agent.chat_manager import ChatManager
from agent.generator import generate_and_load
from config import settings
from shell.golden_shell import GoldenShell
from shell.layout_state import LayoutStateManager
from shell.widget_picker import WidgetPicker
from shell.widget_registry import WidgetRegistry

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger(__name__)

registry = WidgetRegistry()
layout_state = LayoutStateManager(settings.layout_file)
chat_manager = ChatManager(settings.chats_dir)


def _build_welcome() -> pn.viewable.Viewable:
    return pn.pane.Markdown(
        "# Welcome\n\nPanel Agentic UI is running.\n\n"
        "Use the **Chat** panel on the right to describe a widget you need. "
        "The LLM will generate, validate, and hot-load it into this layout.\n\n"
        "You can **drag tabs** to rearrange, **resize** panels by dragging the "
        "borders between them, and **close** tabs with the × button.",
        sizing_mode="stretch_both",
        styles={
            "padding": "2em",
            "background": "#ffffff",
            "color": "#333333",
            "font-family": "system-ui, -apple-system, sans-serif",
        },
    )


def create_app() -> pn.viewable.Viewable:
    """Build the application shell for one browser session."""
    initial_layout = layout_state.load()
    log.info("Loaded layout (%d bytes)", len(initial_layout))

    shell = GoldenShell(
        registry=registry,
        initial_layout_json=initial_layout,
        sizing_mode="stretch_both",
        min_height=600,
        min_width=800,
    )

    def _persist_layout(event):
        if event.new:
            layout_state.save(event.new)

    shell.param.watch(_persist_layout, "layout_json")

    if "welcome" not in registry:
        registry.add("welcome", _build_welcome())

    def _wire_session(session):
        """Connect each chat session to the LLM generator pipeline."""
        async def _on_gen(msg: str) -> bool:
            return await generate_and_load(msg, session, shell, registry, settings)
        session.on_generate = _on_gen

    for session in chat_manager._sessions:
        _wire_session(session)

    _orig_new = chat_manager.new_session
    def _new_session_with_gen() -> "ChatSession":
        session = _orig_new()
        _wire_session(session)
        return session
    chat_manager.new_session = _new_session_with_gen

    registry.add("__chat__", chat_manager.get_panel())

    picker = WidgetPicker(registry=registry, shell=shell, settings=settings)
    registry.add("__widget_picker__", picker.get_panel())

    def _on_ready():
        if '"welcome"' not in initial_layout:
            try:
                shell.add_widget("welcome", "Welcome")
                log.info("Welcome widget added programmatically")
            except Exception:
                log.exception("Failed to add welcome widget")
        if '"__chat__"' not in initial_layout:
            try:
                shell.add_widget("__chat__", "Chat")
                log.info("Chat widget added programmatically")
            except Exception:
                log.exception("Failed to add chat widget")
        if '"__widget_picker__"' not in initial_layout:
            try:
                shell.add_widget("__widget_picker__", "Widget Library")
                log.info("Widget Library added programmatically")
            except Exception:
                log.exception("Failed to add Widget Library")

    pn.state.onload(_on_ready)

    return pn.Column(
        shell,
        sizing_mode="stretch_both",
        margin=0,
        styles={"height": "100vh", "overflow": "hidden"},
    )


pn.extension(
    sizing_mode="stretch_both",
    raw_css=[
        "html, body { margin: 0; padding: 0; overflow: hidden; height: 100%; background: #f5f5f5; }",
        ".bk-root { height: 100%; }",
    ],
)

app = create_app()
app.servable()


if __name__ == "__main__":
    pn.serve(
        {"": create_app},
        address=settings.panel_address,
        port=settings.panel_port,
        title="Panel Agentic UI",
        show=False,
        websocket_origin="*",
    )
