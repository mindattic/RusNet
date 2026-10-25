"""Orchestrate a full scan: tie every discovery module together into one Scan object.

Order is chosen so each step feeds the next: sweep to wake the ARP cache, read ARP for MACs, ask
devices to describe themselves (SSDP/mDNS), resolve names, probe service ports, then reason about
device type and OS from everything gathered.
"""

from __future__ import annotations

import ipaddress
import socket
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from . import classify
from .discovery import arp, dns, interfaces, mdns, oui, ports, ping, ssdp
from .model import Host, Scan


@dataclass
class Options:
    networks: List[str] = field(default_factory=list)  # explicit CIDRs; empty = auto from interfaces
    ping_timeout_ms: int = 800
    ping_workers: int = 128
    port_timeout: float = 0.6
    full_ports: bool = False          # probe the whole COMMON_PORTS map rather than the quick subset
    skip_ports: bool = False
    skip_ssdp: bool = False
    skip_mdns: bool = False
    skip_dns: bool = False
    max_hosts: int = 1024
    discovery_timeout: float = 3.0


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _skip_ip(ip: str) -> bool:
    """True for addresses that aren't real neighbours: loopback, multicast, unspecified, link-local.

    A service on this machine can answer SSDP/mDNS from 127.0.0.1, which would otherwise show up as a
    phantom host, so every discovery source is filtered through this.
    """
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True
    return addr.is_loopback or addr.is_multicast or addr.is_unspecified or addr.is_link_local


def _primary_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return ""


def run(opts: Optional[Options] = None, on_log: Callable[[str], None] = _log) -> Scan:
    opts = opts or Options()
    scan = Scan()

    on_log("[*] Enumerating local interfaces...")
    ifaces = interfaces.discover()
    scan.interfaces = ifaces
    self_ips = {i.ip for i in ifaces if i.ip}
    gateways = {i.gateway for i in ifaces if i.gateway}
    primary = _primary_ip()
    if primary:
        self_ips.add(primary)

    # Decide which networks to sweep.
    nets = list(opts.networks)
    if not nets:
        for i in ifaces:
            if i.cidr and i.cidr not in nets:
                # Skip anything that isn't a private LAN unless the user asked for it explicitly.
                try:
                    net = ipaddress.ip_network(i.cidr, strict=False)
                    # Private LANs only, and only ones with usable host addresses to sweep
                    # (a /31 or /32 - common on VPN adapters - has none).
                    if (net.is_private and not net.is_loopback and not net.is_link_local
                            and net.prefixlen <= 30):
                        nets.append(i.cidr)
                except ValueError:
                    pass
    if not nets and primary:
        nets.append(str(ipaddress.ip_network(primary + "/24", strict=False)))
    scan.networks = nets
    on_log("[*] Networks to scan: " + (", ".join(nets) if nets else "(none found)"))

    # 1) Ping sweep every network.
    ping_results = {}
    for cidr in nets:
        on_log("[*] Ping sweep %s ..." % cidr)
        last = {"n": 0}

        def progress(done: int, total: int) -> None:
            if done - last["n"] >= max(1, total // 10) or done == total:
                last["n"] = done
                on_log("    %d/%d" % (done, total))

        res = ping.sweep(cidr, timeout_ms=opts.ping_timeout_ms, workers=opts.ping_workers,
                         max_hosts=opts.max_hosts, on_progress=progress)
        ping_results.update(res)
    on_log("[+] %d host(s) answered ping." % len(ping_results))

    for ip, pr in ping_results.items():
        h = scan.host_for(ip)
        h.is_up = True
        h.add_source("ping")
        h.rtt_ms = pr.rtt_ms
        h.ttl = pr.ttl

    # 2) ARP table -> MACs (the sweep just populated it).
    on_log("[*] Reading ARP cache...")
    for ip, mac in arp.read_table().items():
        if _skip_ip(ip):
            continue
        h = scan.host_for(ip)
        h.mac = mac
        h.add_source("arp")
        if not h.is_up:
            h.is_up = True  # in ARP but silent to ping: still a real neighbour

    # 3) Device self-advertisements.
    if not opts.skip_ssdp:
        on_log("[*] SSDP (UPnP) discovery...")
        for ip, info in ssdp.discover(timeout=opts.discovery_timeout).items():
            if _skip_ip(ip):
                continue
            h = scan.host_for(ip)
            h.add_source("ssdp")
            h.is_up = True
            if info.get("server"):
                h.details["ssdp_server"] = info["server"]
            if info.get("st"):
                h.details["ssdp_st"] = info["st"]
            if info.get("location"):
                h.details["ssdp_location"] = info["location"]

    if not opts.skip_mdns:
        on_log("[*] mDNS / Bonjour discovery...")
        for ip, info in mdns.discover(timeout=opts.discovery_timeout).items():
            if _skip_ip(ip):
                continue
            h = scan.host_for(ip)
            h.add_source("mdns")
            h.is_up = True
            if info.get("services"):
                h.details["mdns_services"] = info["services"][:30]
            if info.get("names"):
                h.details["mdns_names"] = info["names"][:10]
                if not h.hostname:
                    h.hostname = info["names"][0]

    # 4) Mark self and gateway.
    for h in scan.hosts:
        if h.ip in self_ips:
            h.is_self = True
            h.add_source("self")
            if not h.hostname:
                h.hostname = scan.scanner_host
        if h.ip in gateways:
            h.is_gateway = True

    up_ips = [h.ip for h in scan.hosts if h.is_up]

    # 5) Reverse DNS / NetBIOS names.
    if not opts.skip_dns:
        on_log("[*] Resolving names for %d host(s)..." % len(up_ips))
        for ip, name in dns.resolve_all(up_ips).items():
            h = scan.host_for(ip)
            if not h.hostname:
                h.hostname = name

    # 6) Port probe each live host.
    if not opts.skip_ports:
        port_list = list(ports.COMMON_PORTS.keys()) if opts.full_ports else ports.DEFAULT_PORTS
        on_log("[*] Probing %d service port(s) on %d host(s)..." % (len(port_list), len(up_ips)))

        def probe(ip: str):
            return ip, ports.scan_host(ip, port_list, timeout=opts.port_timeout)

        with ThreadPoolExecutor(max_workers=min(32, max(1, len(up_ips)))) as pool:
            for fut in as_completed([pool.submit(probe, ip) for ip in up_ips]):
                ip, found = fut.result()
                scan.host_for(ip).ports = found

    # 7) Vendor lookup + classification.
    on_log("[*] Identifying vendors and device types...")
    for h in scan.hosts:
        if h.mac and not h.vendor:
            h.vendor = oui.lookup(h.mac)
        classify.classify(h)

    scan.finish()
    on_log("[+] Scan complete: %d hosts, %d up, %d open ports." %
           (scan.stats["total_hosts"], scan.stats["hosts_up"], scan.stats["open_ports"]))
    return scan
