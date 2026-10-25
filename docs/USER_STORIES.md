---
codex: 1
project: RusNet
code: RN
layer: stories
status: living
updated: 2026-10-25
---
<!-- GENERATED from MindAttic.Tickets/data/Tickets.db by `tickets db render`. Do not edit: this file is rewritten from the database; change stories and tickets with the tickets CLI. -->

# RusNet — User Stories
> ✅ done (shipped & tested) · 🟡 partial · ⬜ planned. Every ✅ cites the test.

## Priority backlog
_Nothing recorded yet._

## Tickets
> Permanent log of every change and fix — this repo's ticket system. Rows are append-only: never
> delete or reword one; only move its Status (open → closed / wont-do) and fill in Ref. Status is
> a word, not a glyph, so tickets don't count toward the story index. Keep this section last.

| ID | Date | Type | Status | Summary | Ref |
|---|---|---|---|---|---|
| RN-T1 | 2026-10-25 | docs | closed | Start the permanent ticket log in the ticket database | — |
| RN-T2 | 2026-10-25 | chore | closed | Scaffold RusNet: local-network inventory scanner (Python core, standardized JSON schema v1, self-contained interactive HTML viewer, Python + .NET WebView2 desktop hosts) | — |
| RN-T3 | 2026-10-25 | fix | closed | Fix 4 defects found by /bughunt: mDNS query missing the unicast-response (QU) bit so it returned nothing; OS donut slice/legend filtered every host out (wrong field); network-map leaked internal x/y onto host objects into Copy-as-JSON; dead gw placeholder in the psutil interface path | — |
| RN-T4 | 2026-10-25 | feature | closed | Add a Scan button to the shared viewer toolbar (and empty state) with a scanning overlay, wired through a new window.rusnet.setHostScan hook; the Python app scans in-process and the WPF app shells out to the Python scanner. Strip the WPF native chrome so both desktop apps are the identical web viewer. | — |
| RN-T5 | 2026-10-25 | feature | closed | Add install scripts (install.ps1 + install.sh) that set up a venv and install requirements.txt plus the rusnet CLI; fix requirements.txt which used extra== markers that never install under pip install -r | — |
| RN-T6 | 2026-10-25 | feature | closed | Add install.bat: a double-clickable Windows launcher that lets you choose to install the Python package, build/publish the Windows (.NET WebView2) app, or both; also accepts python\|windows\|both as an argument | — |
| RN-T7 | 2026-10-25 | feature | closed | Replace install.ps1/install.bat/install.sh with a single deploy.ps1/deploy.bat that auto-installs prerequisites via winget and deploys both desktop apps to C:\Apps\RusNet (Windows, Python, vendored rusnet source for the Scan button), cleaning stale output before each republish | deploy.ps1 -Force -Launch run |
| RN-T8 | 2026-10-25 | feature | closed | Default scan output and both desktop apps' Open dialogs to the user's real Downloads folder, resolved via SHGetKnownFolderPath (with registry fallback) instead of a naive USERPROFILE join so a relocated/OneDrive-redirected Downloads folder still resolves correctly | rusnet.paths.get_downloads_dir() |
