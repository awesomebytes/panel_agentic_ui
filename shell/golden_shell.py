"""GoldenLayout v2 shell component for Panel.

GL v2 ships no UMD bundle; the library is loaded at runtime via a dynamic
ESM import from esm.sh.  Initialisation is async, so a pending-queue is used
to absorb add/remove requests that arrive before the layout is ready.

Param contract
──────────────
mount_request         JS → Python   GL created a component container
unmount_request       JS → Python   GL destroyed a component container
layout_json           JS → Python   serialised GL config (debounced 500 ms)
add_widget_request    Python → JS   add a GL component for a named widget
remove_widget_request Python → JS   close the GL component for a named widget
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx
import panel as pn
import param
from panel.reactive import ReactiveHTML

from shell.shortcuts import SHORTCUT_PALETTE_JS

log = logging.getLogger(__name__)

_GL_VERSION = "2.6.0"
_GL_CDN = f"https://cdn.jsdelivr.net/npm/golden-layout@{_GL_VERSION}/dist"
_GL_ESM = f"https://esm.sh/golden-layout@{_GL_VERSION}"

_CSS_BASE = f"{_GL_CDN}/css/goldenlayout-base.css"
_CSS_THEME = f"{_GL_CDN}/css/themes/goldenlayout-light-theme.css"

# ---------------------------------------------------------------------------
# Inline JS helpers stored in `state` so all _scripts callbacks can reuse them
# ---------------------------------------------------------------------------
_JS_INIT_HELPERS = f"""
var GL_ESM_URL = '{_GL_ESM}';

// Build and add a component item to the first viable container
state.addItemToLayout = function(layout, req) {{
    var itemCfg = {{
        type: 'component',
        componentType: 'panel-widget',
        componentState: {{ widget_name: req.name }},
        title: req.title || req.name,
        isClosable: true
    }};
    var root = layout.rootItem;
    if (!root) {{
        try {{
            layout.loadLayout({{ root: {{ type: 'stack', content: [itemCfg] }} }});
        }} catch (e) {{
            console.error('GoldenShell: loadLayout (first item) failed', e);
        }}
        return;
    }}
    // Prefer the first child of root (main area); fall back to root itself
    var target = (root.contentItems && root.contentItems.length > 0)
        ? root.contentItems[0]
        : root;
    try {{
        target.addItem(itemCfg);
    }} catch (e) {{
        console.error('GoldenShell: addItem failed', e, req);
    }}
}};

// Walk the item tree and close the first matching widget
state.removeItemFromLayout = function(layout, name) {{
    function visit(item) {{
        if (!item) return false;
        if (item.type === 'component') {{
            var cs = item.componentState || {{}};
            if (cs.widget_name === name) {{
                try {{ item.close(); }} catch (e) {{
                    console.warn('GoldenShell: close() failed', e);
                }}
                return true;
            }}
        }}
        if (item.contentItems) {{
            var children = item.contentItems.slice();
            for (var i = 0; i < children.length; i++) {{
                if (visit(children[i])) return true;
            }}
        }}
        return false;
    }}
    try {{ visit(layout.rootItem); }} catch (e) {{
        console.error('GoldenShell: removeItemFromLayout failed', e, name);
    }}
}};
"""

_JS_RENDER = (
    _JS_INIT_HELPERS
    + SHORTCUT_PALETTE_JS
    + r"""
var DEFAULT_CFG = {
    root: {
        type: 'row',
        content: [
            { type: 'stack', size: '75%', content: [] },
            { type: 'stack', size: '25%', content: [] }
        ]
    }
};

function parseCfg(s) {
    if (!s) return DEFAULT_CFG;
    try {
        var cfg = JSON.parse(s);
        if (cfg.resolved) {
            // Resolved configs have {size: Number, sizeUnit: "%"|"fr"|"px"}
            // Convert to unresolved format {size: "75%"} and strip resolved flag
            function unresolve(item) {
                if (!item) return item;
                if (typeof item.size === 'number' && item.sizeUnit) {
                    item.size = String(item.size) + (item.sizeUnit === 'fr' ? 'fr' : item.sizeUnit);
                    delete item.sizeUnit;
                }
                delete item.minSizeUnit;
                delete item.id;
                delete item.maximised;
                delete item.reorderEnabled;
                if (item.content && Array.isArray(item.content)) {
                    item.content.forEach(unresolve);
                }
                return item;
            }
            unresolve(cfg.root);
            delete cfg.resolved;
            delete cfg.openPopouts;
            delete cfg.settings;
            delete cfg.dimensions;
            delete cfg.header;
        }
        return cfg;
    } catch (e) {
        console.warn('GoldenShell: invalid layout_json, falling back to default', e);
        return DEFAULT_CFG;
    }
}

// GL v2 has no UMD bundle — use dynamic ESM import
(async function() {
    var glModule;
    try {
        glModule = await import(GL_ESM_URL);
    } catch (err) {
        console.error('GoldenShell: failed to import golden-layout', err);
        gl_host.innerHTML =
            '<p style="color:#f88;font-family:monospace;padding:1em">' +
            'GoldenLayout failed to load:<br>' + String(err) + '</p>';
        return;
    }

    var GoldenLayout = glModule.GoldenLayout;
    if (typeof GoldenLayout !== 'function') {
        console.error('GoldenShell: GoldenLayout constructor not found in module', glModule);
        return;
    }

    // Create a viewport-filling container for GL in the body, bypassing
    // Panel's ReactiveHTML wrapper which may have 0x0 size.
    var glContainer = document.createElement('div');
    glContainer.id = 'gl-container';
    glContainer.style.cssText = 'position:fixed;top:0;left:0;width:100vw;height:100vh;z-index:10;background:#f5f5f5;';
    document.body.appendChild(glContainer);

    // Custom styles for light theme and visible splitters
    var glStyle = document.createElement('style');
    glStyle.textContent = [
        '.lm_splitter { background: #d0d0d0 !important; opacity: 1 !important; }',
        '.lm_splitter:hover { background: #4a90d9 !important; }',
        '.lm_header { background: #e8e8e8 !important; }',
        '.lm_tab { background: #f0f0f0 !important; color: #333 !important; font-family: system-ui, sans-serif !important; }',
        '.lm_tab.lm_active { background: #ffffff !important; border-bottom: 2px solid #4a90d9 !important; }',
        '.lm_content { background: #ffffff !important; }',
        '.lm_controls .lm_popout { display: none !important; }',
        '.lm_close_tab { color: #999 !important; }',
        '.lm_close_tab:hover { color: #e53e3e !important; }',
        '@keyframes gl-shimmer { 0%{background-position:200% 0} 100%{background-position:-200% 0} }',
        '.gl-skeleton { width:100%;height:100%;background:linear-gradient(90deg,#f0f0f0 25%,#e8e8e8 50%,#f0f0f0 75%);background-size:200% 100%;animation:gl-shimmer 1.4s ease-in-out infinite; }',
        '.gl-backend-dot { display:inline-block;width:7px;height:7px;border-radius:50%;margin-left:5px;vertical-align:middle;flex-shrink:0; }',
        '.gl-backend-dot-green { background:#22c55e; }',
        '.gl-backend-dot-red { background:#ef4444; }',
    ].join('\\n');
    document.head.appendChild(glStyle);

    var layout = new GoldenLayout(glContainer);

    // Disable popout (opens blank windows in Panel's server context)
    layout.popoutClickHandler = function() {};

    layout.registerComponentFactoryFunction(
        'panel-widget',
        function(container, componentState) {
            var widgetName = componentState.widget_name;
            var el = container.element;
            el.style.cssText = 'width:100%;height:100%;overflow:hidden;';

            // Show loading skeleton until the Bokeh root arrives
            var skeleton = document.createElement('div');
            skeleton.className = 'gl-skeleton';
            el.appendChild(skeleton);

            function removeSkeleton() {
                if (skeleton.parentNode) skeleton.parentNode.removeChild(skeleton);
            }

            // Snapshot existing body children before requesting mount
            var existingIds = new Set();
            for (var child of document.body.children) {
                existingIds.add(child);
            }

            // Watch for the new Bokeh root div to appear in body
            var observer = new MutationObserver(function(mutations) {
                for (var m of mutations) {
                    for (var node of m.addedNodes) {
                        if (node.nodeType === 1 && !existingIds.has(node) &&
                            node.className && node.className.indexOf('bk-') === 0) {
                            observer.disconnect();
                            removeSkeleton();
                            el.appendChild(node);
                            node.style.cssText = 'width:100%;height:100%;';
                            console.log('[GoldenShell] Reparented Bokeh root for:', widgetName);
                            return;
                        }
                    }
                }
            });
            observer.observe(document.body, { childList: true });

            // Timeout: disconnect observer and clear skeleton after 10s
            setTimeout(function() { observer.disconnect(); removeSkeleton(); }, 10000);

            // Store tab element reference so backend health dots can be injected later
            state.widgetTabs = state.widgetTabs || {};
            setTimeout(function() {
                if (container.tab && container.tab.element) {
                    state.widgetTabs[widgetName] = container.tab.element;
                }
            }, 200);

            data.mount_request = {
                widget: widgetName,
                ts: Date.now()
            };
            container.on('destroy', function() {
                observer.disconnect();
                delete (state.widgetTabs || {})[widgetName];
                data.unmount_request = { widget: widgetName, ts: Date.now() };
            });
        }
    );

    var cfg = parseCfg(data.layout_json);
    // Force settings: no popouts, visible splitters
    cfg.settings = cfg.settings || {};
    cfg.settings.popoutWholeStack = false;
    cfg.settings.blockedPopoutsThrowError = false;
    cfg.settings.showPopoutIcon = false;
    cfg.settings.reorderEnabled = true;
    cfg.header = cfg.header || {};
    cfg.header.popout = false;
    cfg.dimensions = cfg.dimensions || {};
    cfg.dimensions.borderWidth = 6;
    cfg.dimensions.borderGrabWidth = 8;
    cfg.dimensions.headerHeight = 28;
    try {
        layout.loadLayout(cfg);
    } catch (e) {
        console.warn('GoldenShell: loadLayout failed, retrying with default', e);
        DEFAULT_CFG.settings = cfg.settings;
        DEFAULT_CFG.header = cfg.header;
        DEFAULT_CFG.dimensions = cfg.dimensions;
        try { layout.loadLayout(DEFAULT_CFG); }
        catch (e2) { console.error('GoldenShell: default loadLayout also failed', e2); }
    }

    // Debounce stateChanged → layout_json param (500 ms)
    var _stateTimer = null;
    layout.on('stateChanged', function() {
        clearTimeout(_stateTimer);
        _stateTimer = setTimeout(function() {
            try {
                var resolved = layout.saveLayout();
                // Convert ResolvedLayoutConfig → LayoutConfig for reload compatibility
                if (glModule.LayoutConfig && glModule.LayoutConfig.fromResolved) {
                    data.layout_json = JSON.stringify(glModule.LayoutConfig.fromResolved(resolved));
                } else {
                    data.layout_json = JSON.stringify(resolved);
                }
            } catch (e) { console.error('GoldenShell: saveLayout failed', e); }
        }, 500);
    });

    state.layout = layout;

    // Drain any requests queued before layout was ready
    if (state.pendingAdd) {
        state.pendingAdd.forEach(function(req) {
            state.addItemToLayout(layout, req);
        });
        state.pendingAdd = null;
    }
    if (state.pendingRemove) {
        state.pendingRemove.forEach(function(name) {
            state.removeItemFromLayout(layout, name);
        });
        state.pendingRemove = null;
    }
})();
"""
)

_JS_ADD_WIDGET = r"""
var req = data.add_widget_request;
if (!req || !req.name) return;
if (!state.layout) {
    state.pendingAdd = state.pendingAdd || [];
    state.pendingAdd.push(req);
    return;
}
state.addItemToLayout(state.layout, req);
"""

_JS_REMOVE_WIDGET = r"""
var req = data.remove_widget_request;
if (!req || !req.name) return;
if (!state.layout) {
    state.pendingRemove = state.pendingRemove || [];
    state.pendingRemove.push(req.name);
    return;
}
state.removeItemFromLayout(state.layout, req.name);
"""

_JS_MOUNT_DONE = r"""
var info = data.mount_done;
if (!info || !info.widget_name) return;
console.log('[GoldenShell] mount_done signal for:', info.widget_name);
// Reparenting is handled by the MutationObserver set in the factory function.
"""

_JS_BACKEND_HEALTH = r"""
var info = data.backend_health_update;
if (!info || !info.widget_name) return;
var tabEl = (state.widgetTabs || {})[info.widget_name];
if (!tabEl) return;
var existing = tabEl.querySelector('.gl-backend-dot');
if (existing) existing.parentNode.removeChild(existing);
var dot = document.createElement('span');
dot.className = 'gl-backend-dot gl-backend-dot-' + (info.healthy ? 'green' : 'red');
dot.title = info.healthy ? 'Backend healthy' : 'Backend unreachable';
tabEl.appendChild(dot);
"""


class GoldenShell(ReactiveHTML):
    """Full-viewport GoldenLayout v2 window manager.

    Usage
    -----
    registry = WidgetRegistry()
    registry.add('my_widget', some_panel_component)

    shell = GoldenShell(registry=registry, initial_layout_json=layout_json)
    shell.add_widget('my_widget', 'My Widget Title')
    """

    mount_request = param.Dict(
        default={},
        doc="JS→Python: GL created a component container.",
    )
    unmount_request = param.Dict(
        default={},
        doc="JS→Python: GL destroyed a component container.",
    )
    mount_done = param.Dict(
        default={},
        doc="Python→JS: Bokeh root added, JS should reparent it.",
    )
    layout_json = param.String(
        default="",
        doc="Serialised GoldenLayout config JSON, debounced 500 ms from stateChanged.",
    )
    add_widget_request = param.Dict(
        default={},
        doc="Python→JS: add a GL component.",
    )
    remove_widget_request = param.Dict(
        default={},
        doc="Python→JS: remove GL component by widget_name.",
    )
    backend_health_update = param.Dict(
        default={},
        doc="Python→JS: backend health status for a widget tab dot indicator.",
    )

    __css__ = [_CSS_BASE, _CSS_THEME]

    _template = """<div id="gl_host" style="width:100%;height:100vh;position:relative;overflow:hidden;background:#f5f5f5;"></div>"""

    _scripts = {
        "render": _JS_RENDER,
        "add_widget_request": _JS_ADD_WIDGET,
        "remove_widget_request": _JS_REMOVE_WIDGET,
        "mount_done": _JS_MOUNT_DONE,
        "backend_health_update": _JS_BACKEND_HEALTH,
    }

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def __init__(
        self,
        registry,
        initial_layout_json: str = "",
        manifest_path: Path | str | None = None,
        **params: Any,
    ) -> None:
        """
        Parameters
        ----------
        registry:
            A WidgetRegistry (or any object with a ``.get(name)`` method that
            returns a Panel Viewable or None).
        initial_layout_json:
            Serialised GoldenLayout v2 config to load on first render.
            Falls back to the built-in default two-column layout when empty.
        manifest_path:
            Optional path to ``widgets/manifest.json``.  When supplied,
            ``_on_mount`` will read each widget's ``requires_backend`` field
            and asynchronously ping that URL to show a health-status dot on
            the GL tab.
        """
        if initial_layout_json:
            params.setdefault("layout_json", initial_layout_json)
        super().__init__(**params)
        self._registry = registry
        self._manifest_path: Path | None = Path(manifest_path) if manifest_path else None
        self._mounted_roots: dict[str, Any] = {}
        self.param.watch(self._on_mount, "mount_request")
        self.param.watch(self._on_unmount, "unmount_request")

    # ------------------------------------------------------------------
    # Panel ↔ GL DOM mounting
    # ------------------------------------------------------------------

    def _on_mount(self, event: param.parameterized.Event) -> None:
        """Mount a Panel component as a Bokeh root.

        The JS factory function watches for a new div with a matching
        data-mount-id attribute and reparents it into the GL container.
        """
        req = event.new
        if not req or not req.get("widget"):
            return

        widget_name: str = req["widget"]
        mount_id: str = req.get("mount_id", f"pnl-{widget_name}")

        component = self._registry.get(widget_name)
        if component is None:
            log.warning(
                "GoldenShell: no component registered for %r — mount skipped",
                widget_name,
            )
            return

        doc = pn.state.curdoc
        if doc is None:
            log.error("GoldenShell: curdoc is None while mounting %r", widget_name)
            return

        try:
            root = component.get_root(doc)
            doc.add_root(root)
            self._mounted_roots[widget_name] = root
            root_id = root.ref["id"]
            self.mount_done = {
                "widget_name": widget_name,
                "root_id": root_id,
                "ts": time.monotonic(),
            }
            log.info("GoldenShell: mounted %r root_id=%s", widget_name, root_id)
        except Exception:
            log.exception("GoldenShell: failed to mount %r", widget_name)

        if self._manifest_path:
            asyncio.ensure_future(
                self._check_backend_health(widget_name, self._manifest_path)
            )

    async def _check_backend_health(
        self, widget_name: str, manifest_path: Path
    ) -> None:
        """Ping the widget's required backend URL and update the tab dot.

        Reads ``requires_backend`` from the manifest entry for *widget_name*.
        If present, makes an HTTP GET with a 3-second timeout.  The result is
        broadcast back to JS via the ``backend_health_update`` param.
        """
        try:
            if not manifest_path.exists():
                return
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            backend_url: str | None = None
            for entry in data.get("widgets", []):
                if entry.get("name") == widget_name:
                    backend_url = entry.get("requires_backend")
                    break
            if not backend_url:
                return

            healthy = False
            try:
                async with httpx.AsyncClient(timeout=3.0) as client:
                    resp = await client.get(backend_url)
                    healthy = resp.status_code < 500
            except Exception as exc:
                log.debug(
                    "GoldenShell: backend health check failed for %r (%s): %s",
                    widget_name,
                    backend_url,
                    exc,
                )

            self.backend_health_update = {
                "widget_name": widget_name,
                "healthy": healthy,
                "ts": time.monotonic(),
            }
            log.debug(
                "GoldenShell: backend health for %r at %s — %s",
                widget_name,
                backend_url,
                "healthy" if healthy else "down",
            )
        except Exception:
            log.exception(
                "GoldenShell: unexpected error in _check_backend_health for %r",
                widget_name,
            )

    def _on_unmount(self, event: param.parameterized.Event) -> None:
        """Remove the Bokeh root when GL destroys the component container."""
        req = event.new
        if not req or not req.get("widget"):
            return

        widget_name: str = req["widget"]
        root = self._mounted_roots.pop(widget_name, None)
        if root is None:
            return

        doc = pn.state.curdoc
        if doc is None:
            return

        try:
            doc.remove_root(root)
            log.debug("GoldenShell: unmounted %r", widget_name)
        except Exception:
            log.exception("GoldenShell: failed to unmount %r", widget_name)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_widget(self, name: str, title: str) -> None:
        """Signal GL (via JS) to open a new panel for *name*.

        The component must already be registered in the WidgetRegistry;
        otherwise the subsequent mount_request from GL will be silently
        dropped with a warning.

        Raises
        ------
        KeyError
            If *name* is not in the registry at call time.
        """
        if self._registry.get(name) is None:
            raise KeyError(
                f"No component registered for {name!r}; "
                "call registry.add() before add_widget()."
            )
        self.add_widget_request = {"name": name, "title": title, "ts": time.monotonic()}

    def remove_widget(self, name: str) -> None:
        """Signal GL (via JS) to close the panel for *name*.

        Silently does nothing if the widget is not currently open.
        """
        self.remove_widget_request = {"name": name, "ts": time.monotonic()}
