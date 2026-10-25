# MindAttic project agent entrypoint

Read the shared protocol at `..\mindattic-agent-standard\AGENTS.md` and this project's own
documentation (`README.md`, `docs/SCHEMA.md`). Common prompt commands are implemented by the shared
runner; do not add a second copy under a provider-specific command folder.

## Project-specific context

RusNet is a local-network inventory scanner: it maps the network you administer and writes a
standardized JSON report (`docs/SCHEMA.md`, schema v1) plus a self-contained interactive HTML viewer.
Two native desktop hosts wrap that same viewer with native file dialogs - a Python/pywebview app
(`rusnet/desktop.py`) and a .NET WebView2 app (`dotnet/`).

- Scope is deliberately local and benign: ping sweep, ARP read, reverse DNS/NetBIOS, SSDP/mDNS
  self-advertisements, and light TCP connect probes to identify devices. No authentication,
  exploitation, or evasion - keep it that way.
- The HTML viewer reuses MindAttic.Components (themes, Button, Tag, Modal, Toolbar, and the sun/moon
  ThemeToggle). The component sources are vendored under `rusnet/assets/components/` so reports stay
  self-contained; if you change a component upstream, re-copy it here and regenerate the embedded
  `dotnet/RusNet.Viewer/Assets/viewer.htm` with `python -m rusnet viewer -o <that path>`.
- The single source of truth for the report shape is `docs/SCHEMA.md` and `rusnet/model.py`; keep
  them in step.
