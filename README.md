# RusNet

Scan the network you administer and get back everything it will tell you: every reachable device,
what each one is, and how they connect - as a standardized JSON map **and** a single self-contained
interactive HTML page you can open anywhere, with light/dark (sun/moon) themes.

[![Stack](https://img.shields.io/badge/stack-Python%20%2B%20HTML%2FCSS%2FJS%20%2B%20.NET%20WebView2-blue)](#layout)
[![Deps](https://img.shields.io/badge/core-stdlib%20only-brightgreen)](#requirements)
[![UI](https://img.shields.io/badge/UI-MindAttic.Components-6ba3e8)](#the-viewer)
[![Status](https://img.shields.io/badge/status-0.1.0-success)](#status)

RusNet is a home/office **network-inventory** tool in the spirit of Fing or Angry IP Scanner. It is
for networks you own or are authorised to assess. It uses only standard, benign discovery - it does
not attempt to log in to, exploit, or evade anything.

## What it does

- **Finds every device** on your local subnet(s): an ICMP ping sweep, the ARP neighbour table, and
  the self-advertisements devices broadcast on purpose (SSDP/UPnP and mDNS/Bonjour).
- **Identifies each one** as far as it will reveal: hostname (reverse DNS / NetBIOS / mDNS), MAC
  vendor (IEEE OUI), a coarse OS guess (reply TTL), the common service ports it has open (a light TCP
  connect probe with a short banner), and a device-type guess (router, printer, NAS, camera, phone,
  TV, IoT, PC...).
- **Writes a standardized JSON map** (`network-map.json`, schema in [`docs/SCHEMA.md`](docs/SCHEMA.md)).
- **Writes a self-contained interactive report** (`network-map.htm`) - summary tiles, donut/bar
  charts, a radial network map, collapsible device groups, per-device detail, right-click context
  menus, live search, and a sun/moon light/dark toggle. One file, no server, works offline.

The JSON is the interchange format: **any RusNet viewer loads any RusNet JSON**. Send someone a
`.json` and they can render the whole report themselves.

## Install

The core needs only Python 3.9+. The install scripts create a `.venv`, install `requirements.txt`
(pywebview + psutil, for the desktop app and cleaner interface enumeration), and add the `rusnet`
command:

```powershell
.\install.ps1            # Windows (PowerShell); -System to skip the venv
```
```sh
./install.sh            # macOS / Linux; --system to skip the venv
```

Then activate the environment (`.\.venv\Scripts\Activate.ps1` or `source .venv/bin/activate`). You can
also skip the scripts entirely and run the stdlib-only core straight from the checkout with
`python -m rusnet ...`.

## Quick start

```powershell
# No dependencies for the core - just Python 3.9+.
python -m rusnet scan --open                 # scan auto-detected local networks, open the report
python -m rusnet scan -n 192.168.1.0/24      # scan one specific network
python -m rusnet scan --full-ports           # probe the full service-port list
python -m rusnet report network-map.json     # rebuild the HTML from an existing JSON
python -m rusnet viewer --open               # an empty viewer; drop any RusNet JSON onto it
```

Outputs default to `network-map.json` and `network-map.htm` (change with `-o`).

## The viewer, three ways

The same self-contained HTML viewer is the heart of all three surfaces; they differ only in how you
load a file.

| Surface | Load a report | Scan from the app | Run |
|---|---|---|---|
| **HTML report** | drag-drop a `.json`, or the in-page Open button | — (browsers can't scan) | open `network-map.htm` in any browser |
| **Python desktop app** | native OS file dialog | **Scan** button (in-process) | `pip install pywebview` then `python -m rusnet.desktop [file.json]` (or `--scan`) |
| **.NET WebView2 app** | native OS file dialog | **Scan** button (runs `python -m rusnet scan`) | `dotnet run --project dotnet/RusNet.Viewer` (see [`dotnet/README.md`](dotnet/README.md)) |

Both desktop apps are **the same web viewer with no native chrome**, so they look identical; Open,
Scan and the sun/moon toggle live in the page's own toolbar. All three surfaces share one JS contract:
`window.rusnet.load(objectOrJsonString)` renders a report, `setHostOpen(fn)` / `setHostScan(fn)` let a
native host wire its own file dialog and scanner to the toolbar buttons (registering `setHostScan` is
what reveals the Scan button), and `setScanning(bool)` toggles the scanning overlay.

## Layout

```
rusnet/
  scanner.py            orchestrates a full scan into a Scan model
  model.py              the data model (-> docs/SCHEMA.md)
  classify.py           device-type / OS heuristics (offline reasoning only)
  report.py             builds the self-contained HTML (inlines CSS/JS, embeds data)
  cli.py / __main__.py  `python -m rusnet ...`
  desktop.py            pywebview native-window host
  discovery/            interfaces, ping, arp, dns, ports, ssdp, mdns, oui
  data/oui.csv          bundled MAC-vendor prefixes (drop oui-full.txt for the full IEEE set)
  assets/               the viewer (rusnet-viewer.css/js) + vendored MindAttic.Components
dotnet/RusNet.Viewer    .NET 10 WPF + WebView2 host of the same viewer
docs/SCHEMA.md          the report JSON format (v1)
tests/                  stdlib unittest suite
```

## The viewer's look

The report reuses **MindAttic.Components**: the Dark/Light themes, Button, Tag, Modal, Toolbar, and
the sun/moon `ThemeToggle`. Those sources are vendored under `rusnet/assets/components/` so a report
is fully self-contained. If you change a component upstream, re-copy it and regenerate the .NET app's
embedded copy:

```powershell
python -m rusnet viewer -o dotnet/RusNet.Viewer/Assets/viewer.htm
```

## Requirements

- **Core (scan + JSON + HTML report):** Python 3.9+, standard library only.
- **Python desktop app:** `pywebview` (uses the built-in Edge WebView2 runtime on Windows).
- **Cleaner interface enumeration (optional):** `psutil` - without it, RusNet parses `ipconfig`/`ip`.
- **.NET app:** .NET 10 SDK on Windows, `Microsoft.Web.WebView2`.

## Tests

```powershell
python -m unittest discover -s tests          # Python core
dotnet test dotnet/RusNet.Viewer.slnx         # .NET helper tests (NUnit)
```

## Responsible use

Only scan networks you own or have explicit permission to assess. RusNet is built for inventory and
visibility, not intrusion: no authentication attempts, no exploitation, no evasion.

## Status

0.1.0 - working end to end: live scan, JSON map, self-contained report, Python and .NET viewers.
