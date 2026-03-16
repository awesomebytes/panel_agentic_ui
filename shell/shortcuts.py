"""Keyboard shortcut palette — modal overlay triggered by the '?' key."""
from __future__ import annotations

import param
from panel.reactive import ReactiveHTML

SHORTCUTS: list[tuple[str, str]] = [
    ("?", "Toggle shortcut palette"),
    ("Ctrl+Enter", "Send chat message"),
    ("Ctrl+N", "New chat session"),
    ("Escape", "Close palette"),
]

# ---------------------------------------------------------------------------
# Self-contained JS: creates the modal DOM, attaches key listeners once.
# Guards against duplicate initialisation with window._shortcutPalette.
# ---------------------------------------------------------------------------
SHORTCUT_PALETTE_JS: str = r"""
(function() {
    if (window._shortcutPalette) return;

    var overlay = document.createElement('div');
    overlay.id = 'shortcut-palette-overlay';
    overlay.style.cssText = [
        'display:none',
        'position:fixed',
        'top:0',
        'left:0',
        'width:100vw',
        'height:100vh',
        'background:rgba(0,0,0,0.38)',
        'z-index:10000',
        'align-items:center',
        'justify-content:center'
    ].join(';');

    var modal = document.createElement('div');
    modal.style.cssText = [
        'background:#ffffff',
        'border-radius:10px',
        'box-shadow:0 8px 40px rgba(0,0,0,0.18)',
        'padding:32px 40px',
        'min-width:380px',
        'max-width:500px',
        'font-family:system-ui,-apple-system,sans-serif',
        'color:#1a1a1a'
    ].join(';');

    var heading = document.createElement('h3');
    heading.textContent = 'Keyboard Shortcuts';
    heading.style.cssText = 'margin:0 0 20px 0;font-size:17px;font-weight:600;letter-spacing:0.01em;';
    modal.appendChild(heading);

    var pairs = [
        ['?',          'Toggle shortcut palette'],
        ['Ctrl+Enter', 'Send chat message'],
        ['Ctrl+N',     'New chat session'],
        ['Escape',     'Close palette']
    ];
    pairs.forEach(function(pair) {
        var row = document.createElement('div');
        row.style.cssText = [
            'display:flex',
            'justify-content:space-between',
            'align-items:center',
            'padding:9px 0',
            'border-bottom:1px solid #f0f0f0'
        ].join(';');

        var kbd = document.createElement('kbd');
        kbd.textContent = pair[0];
        kbd.style.cssText = [
            'background:#f7f7f7',
            'border:1px solid #d5d5d5',
            'border-radius:5px',
            'padding:3px 9px',
            'font-family:ui-monospace,monospace',
            'font-size:13px',
            'color:#333',
            'box-shadow:0 1px 3px rgba(0,0,0,0.1)',
            'white-space:nowrap'
        ].join(';');

        var desc = document.createElement('span');
        desc.textContent = pair[1];
        desc.style.cssText = 'color:#555;font-size:14px;';

        row.appendChild(kbd);
        row.appendChild(desc);
        modal.appendChild(row);
    });

    var hint = document.createElement('p');
    hint.textContent = 'Press Escape or click outside to close';
    hint.style.cssText = 'margin:18px 0 0 0;font-size:12px;color:#aaa;text-align:center;';
    modal.appendChild(hint);

    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    function show() { overlay.style.display = 'flex'; }
    function hide() { overlay.style.display = 'none'; }
    function toggle() {
        if (overlay.style.display === 'flex') { hide(); } else { show(); }
    }

    overlay.addEventListener('click', function(e) {
        if (e.target === overlay) hide();
    });

    document.addEventListener('keydown', function(e) {
        var tag = (document.activeElement || {}).tagName || '';
        var isEditable = tag === 'INPUT' || tag === 'TEXTAREA' ||
                         (document.activeElement || {}).isContentEditable;
        if (e.key === '?' && !isEditable && !e.ctrlKey && !e.altKey && !e.metaKey) {
            e.preventDefault();
            toggle();
            return;
        }
        if (e.key === 'Escape') { hide(); }
    });

    window._shortcutPalette = { show: show, hide: hide, toggle: toggle };
})();
"""


class ShortcutPalette(ReactiveHTML):
    """Panel component that injects the keyboard-shortcut modal into the page.

    Mount this component anywhere in the served layout; the modal is appended
    to ``document.body`` exactly once (duplicate-guarded) and responds to
    global key events.
    """

    shortcuts: list[tuple[str, str]] = param.List(
        default=SHORTCUTS,
        doc="Shortcut pairs shown in the palette (label, description).",
    )

    _template = '<div id="sp_anchor" style="display:none;width:0;height:0;position:absolute;"></div>'

    _scripts = {"render": SHORTCUT_PALETTE_JS}
