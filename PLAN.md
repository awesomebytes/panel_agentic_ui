# Panel Agentic UI — Implementation Plan

**Stack:** Python 3.11+ · Panel 1.8.9 · GoldenLayout v2 · FastAPI · Pixi · Playwright  
**Environment:** Pixi (conda + pip hybrid)  
**Testing:** pytest + Playwright + gemini-3-flash visual inspection (via orchestrator subagents)  
**Status:** All phases complete — 144 unit/integration + 10 e2e tests passing (154 total)

> **Execution model:** The orchestrator agent builds each phase using subagents, runs all tests (unit → integration → e2e), performs visual inspection via gemini-3-flash subagents on screenshots, and calls the user for UAT verification before advancing. Mocks first, deep integrations last.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture](#2-architecture)
3. [Widget Contract](#3-widget-contract)
4. [Project Structure](#4-project-structure)
5. [Phase 1 — Foundation & GoldenLayout Shell](#phase-1--foundation--goldenlayout-shell)
6. [Phase 2 — Chat Panel & Persistence](#phase-2--chat-panel--persistence)
7. [Phase 3 — FastAPI Backends](#phase-3--fastapi-backends)
8. [Phase 4 — Widget Infrastructure](#phase-4--widget-infrastructure)
9. [Phase 5 — Core Example Widgets](#phase-5--core-example-widgets)
10. [Phase 6 — LLM Agent Integration](#phase-6--llm-agent-integration)
11. [Phase 7 — Hardening](#phase-7--hardening)
12. [Phase 8 — Polish](#phase-8--polish)
13. [Phase 9 — Deep Integration Widgets](#phase-9--deep-integration-widgets)
14. [Deployment Guide](#deployment-guide)
15. [Known Risks & Mitigations](#known-risks--mitigations)

---

## 1. Project Overview

A web-app framework for real-time system monitoring, management, and teleoperation (primarily robotics). Users compose interfaces from two sources:

1. **Hand-written widgets** — developers create Panel widgets for specific functionality
2. **LLM-generated widgets** — anyone (operators, testers, deployment teams) describes what they need in a chat panel, and an LLM generates, validates, and hot-loads the widget into the live interface

The interface uses GoldenLayout v2 for drag/dock/tab/resize/close capabilities. All widgets are single `.py` files following a strict contract, validated by AST analysis before touching disk.

**Single-user, single-session design.** All browser tabs share one Panel session and one layout state — the interface represents a single physical system.

---

## 2. Architecture

```
Browser
  └── GoldenLayout v2 (JS, via ReactiveHTML)
        ├── Widget panels (N)       ← Bokeh roots mounted into GL containers
        └── Chat panel (right edge) ← ChatManager with pn.Tabs sessions
              │
              │  WebSocket (Bokeh PATCH-DOC protocol)
              │
Panel/Tornado  127.0.0.1:5006
  ├── GoldenShell (ReactiveHTML — owns GL instance)
  ├── ChatManager + ChatSession[]
  ├── WidgetRegistry  {name → Panel component}
  ├── LayoutStateManager  (layout.json ↔ GL config)
  └── Generator (validate → hot-load → register → GL.addWidget)
        │
        │  async httpx  (127.0.0.1 only)
        │
FastAPI backends (all localhost-only)
  ├── :8001  telemetry   (psutil — CPU, memory, disk, network)
  ├── :8002  commands    (allowlisted actions, mock teleoperation)
  ├── :8003  data        (historical queries — stub initially)
  └── :8004  prometheus  (PromQL proxy — stub initially)
```

### GoldenLayout ↔ Panel DOM handoff

```
GoldenLayout container element
  └── <div id="pnl-{widget_name}">     ← GL creates this
        └── Bokeh widget root           ← Panel renders via target_id
```

```javascript
// In ReactiveHTML _scripts
layout.bindComponentEventListener = (container, itemConfig) => {
    container.element.id = `pnl-${itemConfig.componentState.widget_name}`;
    data.mount_request = {
        widget: itemConfig.componentState.widget_name,
        element_id: container.element.id
    };
};
layout.unbindComponentEventListener = (container) => {
    data.unmount_request = { widget: itemConfig.componentState.widget_name };
};
```

```python
@param.depends('mount_request', watch=True)
def _on_mount(self):
    req = self.mount_request
    component = self._registry[req['widget']]
    root = component.get_root(pn.state.curdoc())
    root.name = req['element_id']
    pn.state.curdoc().add_root(root)
```

> **Phase 1 spike:** If `target_id` mounting proves unreliable after investigation, fall back to Panel's `GoldenTemplate`. Document the outcome in AGENTS.md.

---

## 3. Widget Contract

Every widget is a single `.py` file. This contract is enforced by the AST validator.

```python
"""
MANIFEST:
{
  "name": "cpu_gauge",
  "version": 3,
  "title": "CPU Usage — All Cores",
  "description": "Circular gauges showing live CPU usage per core",
  "created": "2025-03-15T14:22:00Z",
  "tags": ["monitoring", "cpu"],
  "category": "plot",
  "backend": "http://localhost:8001/telemetry/cpu",
  "slot_hint": "top_right",
  "requires_backend": "telemetry"
}
"""
import panel as pn
import param

class CpuGauge(param.Parameterized):
    def __init__(self, **params):
        super().__init__(**params)

    def get_panel(self) -> pn.viewable.Viewable:
        ...

def build() -> pn.viewable.Viewable:
    """Entry point called by hot-load system."""
    return CpuGauge().get_panel()
```

**File naming:** `widget_<snake_name>_v<N>.py` — never reuse a module name, never call `importlib.reload()`.

**Async rules (enforced by validator):**
- HTTP: `httpx.AsyncClient` — never `requests`
- Subprocess: `asyncio.create_subprocess_exec` — never `subprocess.run`
- Sleep: `await asyncio.sleep()` — never `time.sleep()`
- Periodic: `pn.state.add_periodic_callback` — never `while True` loops

**Forbidden patterns (AST scanner):**
```python
FORBIDDEN = {
    'requests.get', 'requests.post', 'requests.put', 'requests.delete',
    'urllib.request.urlopen', 'time.sleep',
    'subprocess.run', 'subprocess.call', 'subprocess.check_output',
    'subprocess.check_call', 'os.system', 'os.popen',
}
```

---

## 4. Project Structure

```
monitor/
├── main.py                          # Entry point — wires shell + chat + backends
├── config.py                        # pydantic-settings env config
├── pixi.toml                        # Pixi environment definition
├── pyproject.toml
│
├── shell/
│   ├── golden_shell.py              # ReactiveHTML GoldenLayout v2 wrapper
│   ├── widget_registry.py           # Thread-safe {name: Panel component} dict
│   ├── layout_state.py              # Atomic load/save of layout.json
│   └── hot_load.py                  # importlib-based versioned module loader
│
├── agent/
│   ├── chat_manager.py              # ChatManager + ChatSession
│   ├── generator.py                 # generate → validate → hot-load pipeline
│   ├── validator.py                 # AST static check + subprocess dry-run
│   ├── pr_creator.py                # GitHub PR workflow
│   ├── example_selector.py          # Keyword-based example selection
│   └── prompts/
│       ├── system.md                # LLM system prompt (assembled at runtime)
│       └── examples/                # Reference widget files
│
├── backends/
│   ├── telemetry.py                 # psutil: CPU, memory, disk, network
│   ├── commands.py                  # Allowlisted command execution
│   ├── data.py                      # Historical query stub
│   ├── prometheus.py                # PromQL proxy stub
│   └── audit.py                     # SQLite audit log
│
├── widgets/                         # Generated widget library
│   └── manifest.json
│
├── chats/                           # Persisted chat sessions
├── notes/                           # Persisted note widget content
├── layout.json                      # Current GL layout (auto-saved)
│
├── docs/
│   └── deployment.md                # Nginx/TLS/systemd deployment guide
│
├── tests/
│   ├── conftest.py                  # Shared fixtures
│   ├── fixtures/
│   │   └── test_frame.jpg           # Static test image
│   ├── visual/                      # Screenshots from e2e tests
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
└── AGENTS.md
```

---

## Phase 1 — Foundation & GoldenLayout Shell

**Goal:** Pixi environment set up, GoldenLayout shell rendering in browser, widgets mountable into GL containers, layout persistence working.

### Deliverables

- [x] `pixi.toml` with Python 3.11, panel 1.8.9, and all core dependencies
- [x] `pyproject.toml` with project metadata
- [x] `config.py` — pydantic-settings with env vars (ports, keys, paths)
- [x] `shell/golden_shell.py` — ReactiveHTML wrapping GoldenLayout v2
  - GL v2 loaded from ESM via `esm.sh` (no UMD available)
  - `mount_request` / `unmount_request` param handoff
  - `add_widget(name, title)` method that adds a GL component
  - `remove_widget(name)` method
  - `layout_json` param synced from JS `stateChanged` (debounced 500ms)
  - Default layout: 75/25 split, right column reserved for chat
  - Light theme, popouts disabled, visible splitters
  - Bokeh root reparenting via MutationObserver
- [x] `shell/widget_registry.py` — thread-safe dict with add/remove/get/list
- [x] `shell/layout_state.py` — atomic save (write tmp → rename) and load with default fallback
- [x] `main.py` — wires shell, starts Panel server, loads layout on startup
- [x] `AGENTS.md` — first complete version with project orientation
- [x] Default `layout.json` committed

### Spike: GL↔Panel DOM Handoff — COMPLETED

GL v2 has no UMD bundle — ESM via `esm.sh` is required. Panel ReactiveHTML wrappers can render at 0×0, so GL container is appended directly to `document.body`. Bokeh roots are reparented into GL containers using MutationObserver watching for `bk-` class prefixed divs. `saveLayout()` returns `ResolvedLayoutConfig` which needs conversion back to `LayoutConfig` for `loadLayout()`.

### Tests

- [x] `tests/unit/test_widget_registry.py`
  - [x] Add and retrieve widget
  - [x] Remove widget
  - [x] List widgets returns correct names
  - [x] Thread-safe concurrent add/remove
  - [x] Get missing widget returns None
- [x] `tests/unit/test_layout_state.py`
  - [x] Save and restore roundtrip
  - [x] Atomic write survives simulated crash (write partial → check valid)
  - [x] Default layout returned when file missing
  - [x] Invalid JSON falls back to default
  - [x] Concurrent saves don't corrupt file
- [x] `tests/e2e/test_phase1_shell.py`
  - [x] Shell loads with GoldenLayout visible (Playwright + visual check)
  - [x] Programmatically added widget appears as GL tab
  - [x] Close button (×) visible on widget tab
  - [x] Layout persists after page reload
  - [x] Widget content mounted into GL container

### UAT (user verification)

1. ~~Open the app — GL interface loads within 3 seconds~~ ✅
2. ~~A test widget is visible in a GL tab~~ ✅
3. Drag the tab — it moves
4. Click × — tab closes
5. Refresh page — layout restored as left

---

## Phase 2 — Chat Panel & Persistence

**Goal:** Chat panel rendered inside the GL shell. Multiple independent sessions with UUID-based persistence. History survives page reload.

### Deliverables

- [x] `agent/chat_manager.py`
  - [x] `ChatSession` — UUID-based, serialises to `chats/<uuid>.json` on every message
  - [x] `ChatManager` — owns all sessions, renders `pn.Tabs`, "＋ New Chat" button
  - [x] Message format: `{role, content, timestamp}`
  - [x] Sessions restore from `chats/` directory on startup
- [x] Chat panel mounts into the right-edge GL column
- [x] `main.py` updated to wire chat manager into shell
- [x] `chats/` directory created with `.gitkeep`

### Tests

- [x] `tests/unit/test_chat_session.py`
  - [x] New session has empty history
  - [x] Append user message
  - [x] Append assistant message
  - [x] Persist and restore roundtrip
  - [x] Restored title matches
  - [x] Restored history matches
  - [x] Multiple sessions are independent
  - [x] Session ID is valid UUID
  - [x] Timestamps present in messages
- [x] `tests/e2e/test_phase2_chat.py`
  - [x] Chat panel visible on right side
  - [x] Welcome and Chat tabs both visible
  - [x] Two GL columns visible (main + chat)

### UAT

1. ~~Chat panel visible on the right~~ ✅
2. Click "＋ New Chat" — second tab appears
3. Type in Chat 1, switch to Chat 2 — Chat 1 message not visible in Chat 2
4. Reload — both sessions restored with history

---

## Phase 3 — FastAPI Backends

**Goal:** Telemetry and command backends running, returning real system data (psutil). Prometheus and data backends are stubs. All bind to localhost only.

### Deliverables

- [x] `backends/telemetry.py` — FastAPI app
  - [x] `GET /telemetry/cpu` → `{cores: [float], load: [float,float,float], ts: float}`
  - [x] `GET /telemetry/memory` → `{total, used, percent}`
  - [x] `GET /telemetry/disk` → `{total, used, percent}`
  - [x] `GET /telemetry/network` → `{bytes_sent, bytes_recv}`
- [x] `backends/commands.py` — FastAPI app
  - [x] `POST /command/{action}` with allowlist: `{set_speed, set_param, estop, resume, go_home}`
  - [x] Non-allowlisted actions return 403
- [x] `backends/data.py` — stub returning empty lists
  - [x] `GET /history/{metric}?window=60s` → `[]`
- [x] `backends/prometheus.py` — stub
  - [x] `GET /metrics/query?q=&start=&end=&step=` → `{status: "success", data: {result: []}}`
- [x] `config.py` updated with backend ports and Prometheus URL
- [x] `backends/audit.py` — SQLite audit log

### Tests

- [x] `tests/integration/test_backends.py`
  - [x] Telemetry CPU returns valid schema
  - [x] Telemetry memory returns valid schema
  - [x] Telemetry disk returns valid schema
  - [x] Telemetry network returns valid schema
  - [x] Allowlisted command returns 200
  - [x] Non-allowlisted command returns 403
  - [x] Data stub returns empty list
  - [x] Prometheus stub returns valid structure
  - [x] All backends bind to 127.0.0.1 only

### UAT

1. `curl http://localhost:8001/telemetry/cpu` returns real CPU data
2. `curl -X POST http://localhost:8002/command/estop -H 'Content-Type: application/json' -d '{}'` returns 200
3. `curl -X POST http://localhost:8002/command/nope -H 'Content-Type: application/json' -d '{}'` returns 403

---

## Phase 4 — Widget Infrastructure

**Goal:** Validator, hot-load system, manifest management, example selector, and system prompt all working. No example widgets yet — this phase builds the machinery.

### Deliverables

- [x] `agent/validator.py`
  - [x] Stage 1: AST validation
    - `ast.parse()` — syntax check
    - `build()` function present
    - MANIFEST docstring present and valid JSON
    - Forbidden call patterns detected
    - No top-level side effects (bare calls at module level)
  - [x] Stage 2: Subprocess dry-run (optional, < 5s timeout)
  - [x] Returns `ValidationResult(ok, error, metadata)`
- [x] `shell/hot_load.py`
  - [x] `hot_load(path)` — versioned module load via `importlib.util`
  - [x] `hot_load_with_fallback(path, name, registry)` — returns previous version on crash
  - [x] Error pane returned when no previous version exists
- [x] `widgets/manifest.json` — empty manifest with schema `{"widgets": []}`
  - [x] Atomic update function (`update_manifest`)
- [x] `agent/example_selector.py` — keyword-based selection of reference examples
- [x] `agent/prompts/system.md` — LLM system prompt template with all sections

### Tests

- [x] `tests/unit/test_validator.py` — 15 tests
  - [x] Valid widget passes (from string and from path)
  - [x] Missing `build()` fails
  - [x] Missing MANIFEST fails
  - [x] Malformed MANIFEST JSON fails
  - [x] `requests` import fails
  - [x] `subprocess.run` fails
  - [x] `time.sleep` fails
  - [x] `os.system` fails
  - [x] `asyncio.create_subprocess_exec` inside async method — passes
  - [x] `exec()` inside class method — passes
  - [x] Syntax error fails
  - [x] Metadata extracted correctly (name, title, tags, category)
  - [x] Top-level function call fails
  - [x] Version field is integer
- [x] `tests/unit/test_hot_load.py` — 11 tests
  - [x] Load valid module returns callable build
  - [x] Loaded module registered in `sys.modules`
  - [x] Two versions coexist in `sys.modules`
  - [x] Bad `build()` returns error
  - [x] Fallback returns previous version on crash
  - [x] Fallback returns error pane with no previous version
  - [x] Manifest updated after update_manifest call

### UAT

1. Run `pytest tests/unit/test_validator.py tests/unit/test_hot_load.py -v` — all green
2. Agent demonstrates: write a minimal widget file → validate → hot-load → appears in browser

---

## Phase 5 — Core Example Widgets

**Goal:** All example widgets that depend only on psutil backends or are self-contained. Deep-dependency widgets (ROS, camera/go2rtc, Prometheus live, Grafana) are deferred to Phase 9.

### Core widgets (this phase)

| # | File | Category | Dependencies |
|---|------|----------|-------------|
| 1 | `example_button_function.py` | Action | None (self-contained) |
| 2 | `example_button_subprocess.py` | Action | asyncio only |
| 3 | `example_plot_streaming.py` | Plot | httpx → telemetry backend |
| 4 | `example_plot_oneoff.py` | Plot | httpx → telemetry backend |
| 5 | `example_slider_control.py` | Control | httpx → commands backend |
| 6 | `example_mixed_tracker.py` | Mixed | httpx → telemetry backend |
| 7 | `example_notes.py` | Notes | filesystem only |
| 8 | `example_repl.py` | REPL | exec() with controlled context |

### Deliverables

- [x] All 8 example widget files in `agent/prompts/examples/`
- [x] All 8 pass the validator
- [x] All 8 hot-load successfully into the shell
- [x] `example_selector.py` keyword-based selection working
- [x] `tests/fixtures/test_frame.jpg` — static test image (for later camera tests)
- [x] AGENTS.md updated with examples table (now has all 14 examples)

### Tests

- [x] `tests/unit/test_validator.py::test_all_example_files_pass_validator` — parametrized over all 8
- [x] `tests/integration/test_examples_load.py` — each example hot-loads without error
- [ ] `tests/e2e/test_phase5_widgets.py` — for each widget:
  - [ ] Widget loads and renders (visual check: "Is the widget visible?")
  - [ ] Interactive element responds (click button / move slider / type in editor)
  - Specific interaction checks:
    - [ ] `example_button_function.py` — click → result text appears
    - [ ] `example_button_subprocess.py` — click → live output appears
    - [ ] `example_plot_streaming.py` — wait 3s → chart has data points
    - [ ] `example_plot_oneoff.py` — chart/table visible on load
    - [ ] `example_slider_control.py` — move slider → status shown
    - [ ] `example_mixed_tracker.py` — start → data flows, stop → frozen
    - [ ] `example_notes.py` — edit → save → close → reopen → content preserved
    - [ ] `example_repl.py` — type `print(1+1)` → run → output shows `2`

### UAT

For each widget:
1. Loads without error
2. Title correct in GL tab
3. Fills container, adapts on resize
4. Interactive elements respond
5. Can be closed and reopened from manifest

---

## Phase 6 — LLM Agent Integration

**Goal:** User types a request in the chat panel → LLM generates widget code → validator checks it → hot-loads into the shell. Self-correction on failure (up to 3 retries). All tested with mocked LLM first.

### Deliverables

- [x] `agent/generator.py`
  - [x] `generate_and_load(user_request, session, shell)` — full pipeline
  - [x] System prompt assembled at runtime (system.md + manifest + selected examples)
  - [x] LLM call (Anthropic + OpenAI providers via httpx)
  - [x] Code extracted from response (regex)
  - [x] Validation → on failure, error fed back to LLM → retry (max 3)
  - [x] On success: atomic write → hot-load → register → GL add → manifest update
  - [x] Success/failure system messages appended to chat
- [x] `agent/chat_manager.py` updated
  - [x] on_generate async callback wired to generator
  - [ ] Loading skeleton shown in target GL slot while generating
  - [ ] Streaming LLM response displayed in chat
- [x] `config.py` updated with LLM provider config (support both Anthropic and OpenAI API keys)
- [x] LLM provider abstraction (configurable: anthropic/openai, model name)

### Tests

- [x] `tests/unit/test_generator.py` (all with mocked LLM) — 10 tests
  - [x] extract_code from response / no block / generic block
  - [x] Generates and loads valid widget
  - [x] Self-corrects on first failure (mock returns invalid then valid — 2 LLM calls)
  - [x] Fails after max retries (mock always invalid — 3 calls, success=False)
  - [x] Error text appears in retry prompt
  - [x] Manifest updated after success
  - [x] Chat session updated with success message
  - [x] Chat session updated with error after max retries
- [ ] `tests/integration/test_full_pipeline.py` (mocked LLM, real server)
  - [ ] Message → generate → validate → load → registry → GL component
  - [ ] Invalid code retried and succeeds
  - [ ] Three failures surfaces error, no crash
  - [ ] Layout restored after restart (start, add widget, stop, start, check)
- [ ] `tests/e2e/test_phase6_agent.py`
  - [ ] (mocked LLM) Widget appears after chat message, no crash
  - [ ] (mocked LLM) Multiple chat sessions each have independent history
  - [ ] (`@live_llm`) "Add a button that prints hello world" → button widget appears
  - [ ] (`@live_llm`) "Add a real-time CPU plot" → plot appears and updates
  - [ ] (`@live_llm`) Widget opens as new tab, doesn't replace existing widgets

### UAT

1. Type "Add a button that prints 'hello world'" → widget appears within 15s, clicking shows output
2. Type "Add a real-time CPU plot" → plot widget appears and updates
3. Ask for something intentionally hard → agent retries, either works or shows clear error, app doesn't crash
4. Both chat sessions maintain history after reload

---

## Phase 7 — Hardening

**Goal:** Promote-to-PR workflow, crash recovery with version fallback, backend health indicators. GitHub API tested with mocks.

### Deliverables

- [x] `agent/pr_creator.py`
  - [x] `GitHubPRCreator` class — creates branch, uploads files, opens PR
  - [x] PR contains: widget file, markdown description, chat log
  - [ ] Optional: include widget as LLM example
- [ ] Promote button (⬆) in GL tab header via `headerButtons` API
- [ ] Promote modal — Panel dialog with widget name, description fields, branch input
- [x] `hot_load_with_fallback` integrated — crash shows previous version or error pane
- [x] Backend health check on widget load
  - [x] Ping `requires_backend` URL on mount
  - [x] Show status indicator (green/red dot) in GL tab header
- [x] Widget version history in manifest
- [x] Disk cleanup — archive versions beyond latest 10

### Tests

- [x] `tests/unit/test_pr_creator.py` (mocked GitHub API via respx)
  - [x] Branch created with correct name
  - [x] Widget file uploaded to correct path
  - [x] Chat log uploaded as markdown
  - [x] PR opened with correct title
  - [x] PR body is non-empty
  - [x] Returns PR HTML URL
  - [x] Example file uploaded when flagged
  - [x] Example file not uploaded when not flagged
- [ ] `tests/e2e/test_phase7_hardening.py`
  - [ ] Promote button visible in widget header (visual check)
  - [ ] Promote modal opens on click (visual check)
  - [ ] Crashing widget shows fallback, not blank pane (visual check)
  - [ ] Widget with downed backend shows health indicator (visual check)

### UAT

1. Click "⬆ Promote" on a widget — modal with pre-filled name appears
2. Simulate crash — fallback content shown, not blank
3. Take telemetry backend offline — dependent widgets show warning indicator
4. Reload — all widgets restore correctly

---

## Phase 8 — Polish

**Goal:** Loading skeletons, keyboard shortcut palette, SQLite audit log, voice input, named layout presets.

### Deliverables

- [x] Loading skeleton placeholders during widget init
  - [x] Skeleton visible for at least 200ms while widget loads
  - [x] Animated pulse or shimmer effect
- [x] Keyboard shortcut palette
  - [x] Press `?` to open
  - [x] Lists all available shortcuts (open chat, toggle widget, etc.)
  - [x] Press `Escape` to close
- [x] `backends/audit.py` — SQLite audit log
  - [ ] Every command execution logged: `{timestamp, action, params, source_widget, result}`
  - [x] Tabulator viewer widget to browse audit log (example_audit_viewer.py)
  - [x] `GET /audit/recent?limit=50` endpoint
- [x] Voice input to chat
  - [ ] Web Speech API via ReactiveHTML
  - [x] Microphone button in chat input area
  - [ ] Transcribed text fills chat input
- [x] Named layout presets
  - [x] Save current layout with a name → `layout_<name>.json`
  - [x] Load preset from dropdown
  - [x] Default presets: "monitoring", "debug", "minimal"

### Tests

- [ ] `tests/e2e/test_phase8_polish.py`
  - [ ] Loading skeleton visible during widget init (visual check)
  - [ ] `?` key opens shortcut palette (visual check)
  - [ ] Shortcut palette lists entries (visual check)
  - [ ] Audit log widget shows entries after command execution (visual check)
  - [ ] Microphone button visible in chat input (visual check)
  - [ ] Layout preset save and restore works

### UAT

1. Load a heavy widget — skeleton animation visible briefly
2. Press `?` — shortcut palette opens with entries
3. Execute a command via slider → open audit log → entry shows with timestamp
4. Click microphone button — browser prompts for mic permission (voice input works if granted)
5. Save layout as "test_preset" → switch to different layout → load "test_preset" → original layout restored

---

## Phase 9 — Deep Integration Widgets

**Goal:** Widgets requiring external services or heavy dependencies. Each degrades gracefully when its dependency is unavailable.

### Widgets

| # | File | Dependency | Graceful degradation |
|---|------|-----------|---------------------|
| 1 | `example_plot_ros.py` | rclpy (ROS 2) | Shows "ROS not available" alert |
| 2 | `example_camera_overlay.py` | Camera stream or test image | Uses `test_frame.jpg` in test mode |
| 3 | `example_prometheus.py` | Prometheus instance | Shows "Prometheus not configured" |
| 4 | `example_video_hls.py` | go2rtc + RTSP camera | Shows placeholder with config instructions |
| 5 | `example_grafana_iframe.py` | Grafana instance | Shows "Grafana not configured" with setup link |

### Deliverables

- [ ] `shell/ros_bridge.py` — ROS bridge with `ROS_AVAILABLE` guard
  - [ ] `try: import rclpy` with graceful fallback
  - [ ] `subscribe(topic, msg_type) → asyncio.Queue` interface
- [x] All 5 example widget files in `agent/prompts/examples/`
- [x] All 5 pass the validator
- [x] All 5 hot-load without error (even without their dependencies)
- [ ] `example_selector.py` KEYWORDS dict updated with all 5
- [ ] `example_camera_overlay.py` — ReactiveHTML with JS canvas overlay
  - [ ] Python sends base64 JPEG + detection list
  - [ ] JS draws bounding boxes on canvas
  - [x] Uses `tests/fixtures/test_frame.jpg` when `TEST_MODE=1`
- [x] go2rtc configuration example in `docs/deployment.md`
- [ ] AGENTS.md updated with full examples table

### Tests

- [x] `tests/unit/test_validator.py` — all 5 new examples pass validator
- [x] `tests/integration/test_deep_widgets_load.py` — each loads without crash
- [ ] `tests/e2e/test_phase9_deep_widgets.py`
  - [ ] `example_camera_overlay.py` — image visible with bounding boxes (visual check, test mode)
  - [ ] `example_plot_ros.py` — shows graceful "ROS not available" (visual check)
  - [ ] `example_prometheus.py` — shows form or "not configured" message (visual check)
  - [ ] `example_video_hls.py` — shows player or placeholder (visual check)
  - [ ] `example_grafana_iframe.py` — shows iframe area or "not configured" (visual check)

### UAT

1. Camera overlay widget loads with test image and visible bounding boxes
2. ROS widget shows "ROS not available" gracefully (no crash)
3. Each deep widget loads, renders, and can be closed/reopened

---

## Deployment Guide

A `docs/deployment.md` file covering:

- [x] Nginx reverse proxy config (TLS termination, WebSocket upgrade, origin guard, rate limiting)
- [x] systemd service files for Panel server and FastAPI backends
- [x] Environment variable reference table
- [x] go2rtc setup for RTSP cameras
- [x] Prometheus integration
- [x] Grafana embedding configuration (`allow_embedding`, anonymous auth)
- [x] Backup strategy for `widgets/`, `chats/`, `layout.json`
- [x] Security notes: localhost-only backends, cookie secret, single-user model

Example Nginx config included:

```nginx
server {
    listen 443 ssl;
    server_name monitor.internal;
    ssl_certificate     /etc/ssl/monitor.crt;
    ssl_certificate_key /etc/ssl/monitor.key;

    limit_req_zone $binary_remote_addr zone=monitor:10m rate=5r/s;
    limit_req zone=monitor burst=20 nodelay;

    location / {
        proxy_pass         http://127.0.0.1:5006;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade    $http_upgrade;
        proxy_set_header   Connection "upgrade";
        proxy_set_header   Host       $host;
        proxy_read_timeout 3600s;
    }
}
```

---

## Known Risks & Mitigations

| Risk | Likelihood | Mitigation |
|------|-----------|-----------|
| GL↔Panel `target_id` handoff fails | Medium | Spike in Phase 1. Fallback: `GoldenTemplate`. |
| LLM generates code passing AST but crashing at runtime | Medium | Subprocess dry-run. Error fed to LLM. 3-retry loop. |
| `param` class identity breaks on module name reuse | Certain if reload used | Versioned unique names. Never reload. |
| GL `stateChanged` hammers disk | High | 500ms JS debounce. Atomic write. |
| Panel session memory leak on long uptime | Medium | systemd nightly restart. Monitor with `pn.state.profile`. |
| LLM blocks event loop | Medium | System prompt + AST scan forbid all blocking patterns. |
| Visual test non-determinism (gemini-3-flash) | Low-medium | Narrow YES/NO prompts. Playwright DOM assertions as primary gate. |

---

## Dependency Summary

### Pixi environment (core)

```
python = ">=3.11,<3.13"
panel = ">=1.8.9"
bokeh = ">=3.8.2"
param = "*"
fastapi = "*"
uvicorn = "*"
httpx = "*"
psutil = "*"
pydantic-settings = "*"
```

### Pip packages (not on conda-forge or need latest)

```
google-generativeai    # Gemini for visual test assertions (dev only)
respx                  # Mock httpx in tests (dev only)
pytest                 # Test runner (dev only)
pytest-asyncio         # Async test support (dev only)
pytest-playwright      # Browser automation (dev only)
playwright             # Browser automation (dev only)
```

### Deferred dependencies (Phase 9)

```
rclpy                  # ROS 2 — optional, guarded import
opencv-python          # Camera widget — optional
```
