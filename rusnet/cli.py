"""RusNet command line: scan a network, or build a report/viewer from existing JSON.

    python -m rusnet scan                      # scan auto-detected local networks
    python -m rusnet scan -n 192.168.1.0/24    # scan a specific CIDR
    python -m rusnet scan --full-ports         # probe the full service-port list
    python -m rusnet report scan.json          # build an HTML report from an existing JSON
    python -m rusnet viewer                     # build an empty viewer (load files into it)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import webbrowser

from . import __version__
from .model import Scan
from .paths import get_downloads_dir
from .report import build_html, write_report
from .scanner import Options, run


def _add_scan_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("-n", "--network", action="append", default=[], metavar="CIDR",
                   help="network to scan, e.g. 192.168.1.0/24 (repeatable; default: auto-detect)")
    p.add_argument("--full-ports", action="store_true", help="probe the full service-port list, not the quick subset")
    p.add_argument("--no-ports", action="store_true", help="skip TCP service probing")
    p.add_argument("--no-ssdp", action="store_true", help="skip SSDP/UPnP discovery")
    p.add_argument("--no-mdns", action="store_true", help="skip mDNS/Bonjour discovery")
    p.add_argument("--no-dns", action="store_true", help="skip reverse-DNS / NetBIOS name lookups")
    p.add_argument("--ping-timeout", type=int, default=800, metavar="MS", help="per-host ping timeout (ms)")
    p.add_argument("--max-hosts", type=int, default=1024, metavar="N", help="cap hosts swept per network")
    p.add_argument("-o", "--out", default=None, metavar="NAME",
                   help="output basename; writes <name>.json and <name>.htm "
                        "(default: network-map in the user's Downloads folder)")
    p.add_argument("--open", action="store_true", help="open the HTML report in the default browser when done")


def cmd_scan(args: argparse.Namespace) -> int:
    opts = Options(
        networks=args.network,
        ping_timeout_ms=args.ping_timeout,
        full_ports=args.full_ports,
        skip_ports=args.no_ports,
        skip_ssdp=args.no_ssdp,
        skip_mdns=args.no_mdns,
        skip_dns=args.no_dns,
        max_hosts=args.max_hosts,
    )
    scan = run(opts)

    out = args.out or os.path.join(get_downloads_dir(), "network-map")
    json_path = out + ".json"
    html_path = out + ".htm"
    out_dir = os.path.dirname(json_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(scan.to_dict(), fh, ensure_ascii=False, indent=2)
    write_report(scan, html_path)
    print("[+] Wrote %s" % os.path.abspath(json_path))
    print("[+] Wrote %s" % os.path.abspath(html_path))
    if args.open:
        webbrowser.open("file://" + os.path.abspath(html_path))
    return 0


def _load_scan(path: str) -> Scan:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    scan = Scan()
    # Rehydrate just enough for the report; the report re-serialises from the model.
    from .model import Host, Interface, Port
    scan.tool = data.get("tool", "RusNet")
    scan.version = data.get("version", __version__)
    scan.scanner_host = data.get("scanner_host", "")
    scan.started_at = data.get("started_at", "")
    scan.finished_at = data.get("finished_at", "")
    scan.networks = data.get("networks", [])
    scan.stats = data.get("stats", {})
    for i in data.get("interfaces", []):
        scan.interfaces.append(Interface(**{k: i.get(k) for k in Interface.__annotations__ if k in i}))
    for h in data.get("hosts", []):
        host = Host(ip=h.get("ip", ""))
        for k in ("mac", "vendor", "hostname", "is_up", "is_self", "is_gateway",
                  "rtt_ms", "ttl", "os_guess", "device_type", "model"):
            if k in h:
                setattr(host, k, h[k])
        host.sources = h.get("sources", [])
        host.details = h.get("details", {})
        host.ports = [Port(number=p["number"], service=p.get("service", ""), banner=p.get("banner", ""))
                      for p in h.get("ports", [])]
        scan.hosts.append(host)
    return scan


def cmd_report(args: argparse.Namespace) -> int:
    scan = _load_scan(args.json)
    out = args.out or (os.path.splitext(args.json)[0] + ".htm")
    write_report(scan, out)
    print("[+] Wrote %s" % os.path.abspath(out))
    if args.open:
        webbrowser.open("file://" + os.path.abspath(out))
    return 0


def cmd_viewer(args: argparse.Namespace) -> int:
    html = build_html(None, title="RusNet - Viewer")
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(html)
    print("[+] Wrote empty viewer %s" % os.path.abspath(args.out))
    if args.open:
        webbrowser.open("file://" + os.path.abspath(args.out))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="rusnet", description="RusNet - local network inventory scanner.")
    p.add_argument("--version", action="version", version="RusNet " + __version__)
    sub = p.add_subparsers(dest="command", required=True)

    ps = sub.add_parser("scan", help="scan the local network and write JSON + HTML")
    _add_scan_args(ps)
    ps.set_defaults(func=cmd_scan)

    pr = sub.add_parser("report", help="build an HTML report from an existing RusNet JSON file")
    pr.add_argument("json", help="path to a RusNet JSON file")
    pr.add_argument("-o", "--out", default="", help="output .htm path (default: alongside the JSON)")
    pr.add_argument("--open", action="store_true", help="open the report when done")
    pr.set_defaults(func=cmd_report)

    pv = sub.add_parser("viewer", help="build an empty HTML viewer to load JSON files into")
    pv.add_argument("-o", "--out", default="rusnet-viewer.htm", help="output .htm path")
    pv.add_argument("--open", action="store_true", help="open the viewer when done")
    pv.set_defaults(func=cmd_viewer)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\n[!] Interrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
