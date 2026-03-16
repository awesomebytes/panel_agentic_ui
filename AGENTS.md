# AGENTS.md — Panel Agentic UI Agent Guide

## What this project is

An LLM-agent-driven monitoring, debugging, and teleoperation web interface. Users describe widgets in plain language; the LLM agent generates Panel Python widgets, validates them via AST analysis, and hot-loads them into a GoldenLayout v2 shell. Every widget is a versioned `.py` file stored under `widgets/`. The agent pipeline runs: user request → system prompt (with examples) → LLM → code extraction → AST validation → versioned file write → hot-load via importlib → GoldenLayout shell registration.

## Before you write any code

1. Read this file completely.
2. Run `pixi run pytest tests/unit/ -v` — all must pass before you start.
3. Check `widgets/manifest.json` — never generate a widget that already exists.
4. Review `agent/prompts/examples/` — pick the closest example as a template.

## Critical rules

- **Never call `importlib.reload()`** — always load a new versioned module name.
- **Never block the Panel event loop.** Use `httpx.AsyncClient`, not `requests`. Use `asyncio.create_subprocess_exec`, not `subprocess.run`. Use `await asyncio.sleep()`, not `time.sleep()`.
- **GoldenLayout `stateChanged` fires on every pixel of drag.** Debounced 500ms in JS. Atomic write in Python.
- **Stop periodic callbacks on widget unmount** via the unbind handler.
- **Chat session IDs are UUIDs.** Never use sequential integers.
- **Validator runs before any file touches disk.**
- **No bare top-level expressions** (other than the MANIFEST module docstring). All module-level code must be assignments, imports, or definitions.
- **MANIFEST `version` must be an integer**, not a string.
- **Forbidden call patterns** (validator rejects these): `requests.get/post/put/delete`, `urllib.request.urlopen`, `time.sleep`, `subprocess.run/call/check_output/check_call`, `os.system`, `os.popen`.

## Project structure

```
shell/golden_shell.py       — ReactiveHTML GoldenLayout v2 wrapper
shell/widget_registry.py    — Thread-safe {name: component} dict
shell/layout_state.py       — Atomic save/load of layout.json
shell/hot_load.py           — Versioned module loader (importlib) + manifest updater
shell/shortcuts.py          — Keyboard shortcut bindings
shell/widget_picker.py      — Widget Library: browse examples + generated widgets, add to shell
shell/promote_dialog.py     — PR promotion dialog for widgets

agent/chat_manager.py       — ChatManager + ChatSession (UUID session IDs)
agent/generator.py          — Generate → validate → hot-load pipeline (MAX_RETRIES=3)
agent/validator.py          — AST static check (Stage 1) + subprocess dry-run (Stage 2)
agent/pr_creator.py         — GitHub PR workflow
agent/example_selector.py   — Keyword-based example selection
agent/prompts/system.md     — LLM system prompt template
agent/prompts/examples/     — 14 reference widget files (see table below)

backends/telemetry.py       — psutil: CPU, memory, disk, network (port 8001)
backends/commands.py        — Allowlisted command execution (port 8002)
backends/data.py            — Historical query stub (port 8003)
backends/prometheus.py      — PromQL proxy stub (port 8004)
backends/audit.py           — SQLite audit log (port 8005)

config.py                   — pydantic-settings env config (prefix: MONITOR_)
main.py                     — Entry point
tests/unit/                 — Fast unit tests (no I/O)
tests/integration/          — Integration tests (needs backends running)
tests/e2e/                  — End-to-end tests (needs full app + Playwright)
widgets/                    — Generated widget .py files + manifest.json
chats/                      — Persisted chat session JSON files
notes/                      — Notes markdown files
layout.json                 — Persisted GoldenLayout state
```

## Widget contract

Every widget is a single `.py` file with:

1. **MANIFEST module docstring** — must be the very first statement, valid JSON with all required fields:
   ```json
   {
     "name": "snake_case_name",
     "version": 1,
     "title": "Human Readable Title",
     "description": "One-line description",
     "tags": ["tag1", "tag2"],
     "category": "CategoryName"
   }
   ```
2. **A class extending `param.Parameterized`** with a `get_panel()` method returning a Panel component.
3. **A `build()` function** at module level as the sole entry point — called by the hot-loader.
4. **File naming**: `widget_<snake_name>_v<N>.py` (e.g. `widget_cpu_plot_v2.py`).

Periodic callbacks must be registered with `pn.state.add_periodic_callback()` and stopped on component destruction via a `param.watch` on `"objects"`.

## Available backends

| URL | Method | Response |
|-----|--------|----------|
| http://localhost:8001/telemetry/cpu | GET | `{cores, load, ts}` |
| http://localhost:8001/telemetry/memory | GET | `{total, used, percent}` |
| http://localhost:8001/telemetry/disk | GET | `{total, used, percent}` |
| http://localhost:8001/telemetry/network | GET | `{bytes_sent, bytes_recv}` |
| http://localhost:8002/command/{action} | POST | `{status, action, ts}` |
| http://localhost:8003/history/{metric} | GET | `[{ts, value}]` |
| http://localhost:8004/metrics/query | GET | Prometheus JSON |
| http://localhost:8005/audit/recent?limit=N | GET | `[{ts, action, user, details}]` |

## Config settings (env prefix `MONITOR_`)

| Setting | Default | Description |
|---------|---------|-------------|
| `panel_address` | `127.0.0.1` | Panel server bind address |
| `panel_port` | `5006` | Panel server port |
| `telemetry_port` | `8001` | Telemetry backend port |
| `commands_port` | `8002` | Commands backend port |
| `data_port` | `8003` | Historical data backend port |
| `prometheus_port` | `8004` | Prometheus proxy port |
| `llm_provider` | `anthropic` | `"anthropic"` or `"openai"` |
| `llm_model` | `claude-sonnet-4-20250514` | Model identifier |
| `widgets_dir` | `widgets` | Directory for generated widget files |
| `chats_dir` | `chats` | Directory for chat session files |
| `notes_dir` | `notes` | Directory for notes files |
| `test_mode` | `false` | Disables external I/O in tests |

## Running tests

```bash
pixi run pytest tests/unit/ -v          # Unit tests (fast, no I/O)
pixi run pytest tests/integration/ -v   # Integration (needs backends)
pixi run pytest tests/e2e/ -v           # E2E (needs full app + Playwright)
```

## Validate a widget before using it

```bash
pixi run python -c "from agent.validator import validate; r = validate(open('path/to/widget.py').read()); print('OK' if r.ok else r.error)"
```

## Example widgets reference

| File | Name | Category | Key technique |
|------|------|----------|---------------|
| `example_plot_streaming.py` | `plot_streaming` | Plot | Periodic callback + Bokeh DataSource streaming |
| `example_plot_oneoff.py` | `plot_oneoff` | Plot | One-shot async fetch, no periodic callback |
| `example_plot_ros.py` | `plot_ros` | ROS | ROS 2 topic polling + Bokeh streaming |
| `example_mixed_tracker.py` | `mixed_tracker` | Mixed | User-controlled start/stop periodic callbacks |
| `example_slider_control.py` | `slider_control` | Control | Slider widget → POST to command backend |
| `example_button_function.py` | `button_function` | Action | Button triggers Python function |
| `example_button_subprocess.py` | `button_subprocess` | Action | `asyncio.create_subprocess_exec` + live output |
| `example_repl.py` | `repl` | REPL | Restricted `exec()` context + TextAreaInput |
| `example_notes.py` | `notes` | Notes | File persistence with atomic save |
| `example_grafana_iframe.py` | `grafana_iframe` | Monitoring | Grafana embed via `pn.pane.HTML` iframe |
| `example_prometheus.py` | `prometheus` | Monitoring | PromQL query via httpx async + DataFrame display |
| `example_video_hls.py` | `video_hls` | Video | HLS stream via custom ReactiveHTML/HTML pane |
| `example_camera_overlay.py` | `camera_overlay` | Camera | Camera feed HTML/JS with detection box overlay |
| `example_audit_viewer.py` | `audit_viewer` | Audit | Tabulator with periodic refresh from audit backend |
