"""RusNet desktop app (Python): the viewer in a native window with native file dialogs.

Wraps the self-contained HTML viewer in a pywebview window so loading a report uses the OS file
picker instead of an in-page upload. The window exposes a small JS bridge (`window.pywebview.api`)
with open_file / scan_now, and on load wires the viewer's `rusnet.setHostOpen` hook to it.

    python -m rusnet.desktop                 # open the viewer
    python -m rusnet.desktop scan.json       # open and load a report
    python -m rusnet.desktop --scan          # run a scan, then show it

Needs pywebview:  pip install pywebview   (on Windows it uses the built-in Edge WebView2 runtime).
"""

from __future__ import annotations

import json
import os
import sys
import threading

from .paths import get_downloads_dir
from .report import build_html


class Api:
    """Methods callable from the page as window.pywebview.api.<name>()."""

    def __init__(self) -> None:
        self._window = None

    def bind(self, window) -> None:
        self._window = window

    def open_file(self):
        """Show a native open dialog; return the chosen file's text (or None if cancelled)."""
        import webview

        result = self._window.create_file_dialog(
            webview.OPEN_DIALOG,
            directory=get_downloads_dir(),
            allow_multiple=False,
            file_types=("RusNet report (*.json)", "All files (*.*)"),
        )
        if not result:
            return None
        path = result[0] if isinstance(result, (list, tuple)) else result
        try:
            with open(path, encoding="utf-8") as fh:
                return fh.read()
        except OSError as exc:
            return json.dumps({"__error__": str(exc)})

    def scan_now(self):
        """Run a live scan and return the report JSON as text. Runs on a pywebview worker thread, so
        the window stays responsive; errors come back as {"__error__": ...} for the page to show."""
        try:
            from .scanner import Options, run

            scan = run(Options(), on_log=lambda m: None)
            return json.dumps(scan.to_dict(), ensure_ascii=False)
        except Exception as exc:  # pragma: no cover - defensive, surfaced to the user
            return json.dumps({"__error__": str(exc)})


_WIRE_JS = """
(function () {
  function wire() {
    if (!window.rusnet || !window.pywebview) { return setTimeout(wire, 50); }
    window.rusnet.setHostOpen(function () {
      window.pywebview.api.open_file().then(function (txt) { if (txt) window.rusnet.load(txt); });
    });
    // scan_now runs on a pywebview worker thread, so the window stays responsive; show the overlay
    // around it and load the result (or a readable error) when it returns.
    window.rusnet.setHostScan(function () {
      window.rusnet.setScanning(true);
      window.pywebview.api.scan_now().then(function (txt) {
        window.rusnet.setScanning(false);
        if (!txt) return;
        try {
          var obj = JSON.parse(txt);
          if (obj && obj.__error__) { alert('Scan failed: ' + obj.__error__); return; }
        } catch (e) {}
        window.rusnet.load(txt);
      }).catch(function (e) {
        window.rusnet.setScanning(false);
        alert('Scan failed: ' + e);
      });
    });
  }
  wire();
})();
"""


def run_app(initial_json: str = "", do_scan: bool = False) -> int:
    try:
        import webview
    except ImportError:
        print("pywebview is not installed. Run:  pip install pywebview", file=sys.stderr)
        return 2

    data = None
    if do_scan:
        from .scanner import Options, run as run_scan
        data = run_scan(Options())
    html = build_html(data, title="RusNet")

    api = Api()
    window = webview.create_window("RusNet", html=html, width=1280, height=840, js_api=api)
    api.bind(window)

    def on_loaded() -> None:
        window.evaluate_js(_WIRE_JS)
        if initial_json and not do_scan:
            try:
                with open(initial_json, encoding="utf-8") as fh:
                    text = fh.read()
                # json.dumps makes it a safe JS string literal.
                window.evaluate_js("window.rusnet.load(%s)" % json.dumps(text))
            except OSError as exc:
                print("Could not open %s: %s" % (initial_json, exc), file=sys.stderr)

    window.events.loaded += on_loaded
    webview.start()
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    do_scan = "--scan" in argv
    argv = [a for a in argv if a != "--scan"]
    initial = argv[0] if argv else ""
    return run_app(initial_json=initial, do_scan=do_scan)


if __name__ == "__main__":
    raise SystemExit(main())
