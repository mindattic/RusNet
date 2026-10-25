"""Build the self-contained HTML report / viewer.

The same HTML serves three purposes: a one-off report with a scan embedded, an empty viewer shell a
native host loads files into, and a drag-drop viewer in a plain browser. All CSS and JS are inlined
so a single .htm file is fully self-contained and works offline. The MindAttic.Components themes,
button, tag, modal, toolbar and the sun/moon ThemeToggle are reused from the bundled assets.
"""

from __future__ import annotations

import json
import os
from typing import Optional

from .model import Scan

_ASSETS = os.path.join(os.path.dirname(__file__), "assets")
_COMPONENTS = os.path.join(_ASSETS, "components")


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _bundle_css() -> str:
    parts = []
    # Themes first (dark is :root, light overrides), then components, then the viewer's own CSS.
    for rel in ("dark.css", "light.css", "button.css", "icon-button.css",
                "toolbar.css", "tag.css", "modal.css", "theme-toggle.css"):
        parts.append("/* --- components/%s --- */\n%s" % (rel, _read(os.path.join(_COMPONENTS, rel))))
    parts.append("/* --- rusnet-viewer.css --- */\n" + _read(os.path.join(_ASSETS, "rusnet-viewer.css")))
    return "\n\n".join(parts)


def _bundle_js() -> str:
    parts = [
        "/* --- components/theme-toggle.js --- */\n" + _read(os.path.join(_COMPONENTS, "theme-toggle.js")),
        "/* --- rusnet-viewer.js --- */\n" + _read(os.path.join(_ASSETS, "rusnet-viewer.js")),
    ]
    return "\n\n".join(parts)


_BODY = """
<div class="ma-toolbar rn-toolbar">
  <div class="rn-toolbar__brand">
    <svg class="rn-logo" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
         stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="3"></circle>
      <circle cx="5" cy="6" r="2"></circle><circle cx="19" cy="6" r="2"></circle>
      <circle cx="5" cy="18" r="2"></circle><circle cx="19" cy="18" r="2"></circle>
      <path d="M7 7l3 3M17 7l-3 3M7 17l3-3M17 17l-3-3"></path>
    </svg>
    <span>RusNet</span>
  </div>
  <span class="ma-toolbar__label">network map</span>
  <div class="rn-toolbar__spacer"></div>
  <input id="rn-search" class="rn-search" type="search" placeholder="Search hosts, IPs, ports, vendors..." />
  <button class="ma-btn rn-hidden" data-rn-scan
          style="--ma-btn-u:0.85rem;--ma-btn-bg:var(--bg3);--ma-btn-border:var(--border);--ma-btn-hover-bg:var(--accent);--ma-btn-hover-border:var(--accent);--ma-btn-fg:var(--text);">Scan network</button>
  <button class="ma-btn" data-rn-open
          style="--ma-btn-u:0.85rem;--ma-btn-bg:var(--accent);--ma-btn-border:var(--accent);--ma-btn-hover-bg:var(--text);--ma-btn-hover-border:var(--text);--ma-btn-fg:#fff;">Open report&hellip;</button>
  <button class="ma-theme-toggle" aria-label="Toggle theme"></button>
  <div class="rn-toolbar__meta" id="rn-meta"></div>
</div>

<input id="rn-file" type="file" accept=".json,application/json" style="display:none" />

<div class="rn-wrap">
  <div id="rn-empty" class="rn-empty rn-hidden">
    <h2>No report loaded</h2>
    <p>Scan your network, open a RusNet <code>network-map.json</code> file, or drag one anywhere onto this window.</p>
    <div style="display:flex;gap:10px;justify-content:center;flex-wrap:wrap;">
      <button class="ma-btn rn-hidden" data-rn-scan
              style="--ma-btn-bg:var(--accent);--ma-btn-border:var(--accent);--ma-btn-hover-bg:var(--text);--ma-btn-hover-border:var(--text);--ma-btn-fg:#fff;">Scan this network</button>
      <button class="ma-btn" data-rn-open>Open a report</button>
    </div>
  </div>

  <div id="rn-content" class="rn-hidden">
    <section class="rn-section">
      <div class="rn-section__head"><h2>Summary</h2></div>
      <div class="rn-section__body"><div id="rn-stats" class="rn-stats"></div></div>
    </section>

    <section class="rn-section">
      <div class="rn-section__head"><h2>Breakdown</h2></div>
      <div class="rn-section__body"><div id="rn-charts" class="rn-charts"></div></div>
    </section>

    <section class="rn-section">
      <div class="rn-section__head"><h2>Network map</h2></div>
      <div class="rn-section__body"><div id="rn-map" class="rn-map-wrap"></div></div>
    </section>

    <section class="rn-section">
      <div class="rn-section__head"><h2>Devices</h2><span id="rn-filter-note" class="rn-section__count"></span></div>
      <div class="rn-section__body"><div id="rn-devices" class="rn-devices"></div></div>
    </section>
  </div>
</div>

<div id="rn-drop" class="rn-drop"><div class="rn-drop__box">Drop a RusNet JSON file to load it</div></div>

<div id="rn-scanning" class="rn-scanning">
  <div class="rn-scanning__box">
    <div class="rn-spinner" aria-hidden="true"></div>
    <div class="rn-scanning__text">Scanning the network&hellip;</div>
    <div class="rn-scanning__sub">Sweeping hosts, reading ARP, asking devices to describe themselves.</div>
  </div>
</div>

<div id="rn-detail" class="ma-modal rn-detail">
  <div class="ma-modal__dialog">
    <div class="ma-modal__header">
      <span class="ma-modal__title" id="rn-detail-title">Device</span>
      <button class="ma-modal__close" data-rn-close aria-label="Close">&times;</button>
    </div>
    <div class="rn-detail__body" id="rn-detail-body"></div>
  </div>
</div>

<div id="rn-ctx" class="rn-ctx"></div>
<div id="rn-toast" class="rn-toast"></div>
"""


_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700&display=swap" rel="stylesheet">
<script>
  /* Apply the saved / OS theme before first paint to avoid a flash. */
  try {{
    var t = localStorage.getItem('ma-theme');
    if (t !== 'light' && t !== 'dark')
      t = (window.matchMedia && matchMedia('(prefers-color-scheme: light)').matches) ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', t);
  }} catch (e) {{ document.documentElement.setAttribute('data-theme', 'dark'); }}
</script>
<style>
{css}
</style>
</head>
<body>
{body}
<script>
{data}
</script>
<script>
{js}
</script>
</body>
</html>
"""


def build_html(scan: Optional[Scan] = None, title: str = "RusNet - Network Map") -> str:
    """Return the complete self-contained HTML. With a scan, it is embedded; without, it's a viewer."""
    if scan is not None:
        payload = json.dumps(scan.to_dict(), ensure_ascii=False)
        # Guard against an accidental </script> inside any banner string.
        payload = payload.replace("</", "<\\/")
        data_block = "window.__RUSNET_DATA__ = " + payload + ";"
    else:
        data_block = "/* no embedded data - load a file via the toolbar or drag-drop */"

    return _TEMPLATE.format(
        title=title,
        css=_bundle_css(),
        body=_BODY,
        data=data_block,
        js=_bundle_js(),
    )


def write_report(scan: Optional[Scan], path: str, title: str = "RusNet - Network Map") -> str:
    html = build_html(scan, title=title)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html)
    return path
