"""Data model for a RusNet scan.

Everything a scan learns is held in these dataclasses and serialised to the JSON report. Keeping the
shape in one place means the HTML report and the JSON file never drift apart.
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import socket
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).astimezone().isoformat(timespec="seconds")


@dataclass
class Port:
    """A TCP port found open on a host, with the service we expect to sit behind it."""

    number: int
    service: str = ""
    banner: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"number": self.number, "service": self.service, "banner": self.banner}


@dataclass
class Host:
    """A single device discovered on the network and everything we could glean about it."""

    ip: str
    mac: str = ""
    vendor: str = ""
    hostname: str = ""
    # How we first saw it: "arp", "ping", "ssdp", "mdns", "self".
    sources: List[str] = field(default_factory=list)
    is_up: bool = True
    is_self: bool = False
    is_gateway: bool = False
    rtt_ms: Optional[float] = None
    ttl: Optional[int] = None
    os_guess: str = ""
    device_type: str = ""
    model: str = ""
    ports: List[Port] = field(default_factory=list)
    # Free-form extras a protocol revealed (SSDP headers, mDNS TXT records, etc.).
    details: Dict[str, Any] = field(default_factory=dict)

    def add_source(self, src: str) -> None:
        if src not in self.sources:
            self.sources.append(src)

    def to_dict(self) -> Dict[str, Any]:
        d = dataclasses.asdict(self)
        d["ports"] = [p.to_dict() for p in self.ports]
        return d


@dataclass
class Interface:
    """One of the scanning machine's own network adapters."""

    name: str
    ip: str = ""
    mac: str = ""
    netmask: str = ""
    cidr: str = ""
    gateway: str = ""
    dns: List[str] = field(default_factory=list)
    dhcp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class Scan:
    """A complete scan: the machine that ran it, the networks probed, and every host found."""

    started_at: str = field(default_factory=_now)
    finished_at: str = ""
    scanner_host: str = field(default_factory=socket.gethostname)
    tool: str = "RusNet"
    version: str = "0.1.0"
    networks: List[str] = field(default_factory=list)
    interfaces: List[Interface] = field(default_factory=list)
    hosts: List[Host] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)

    def host_for(self, ip: str) -> Host:
        for h in self.hosts:
            if h.ip == ip:
                return h
        h = Host(ip=ip)
        self.hosts.append(h)
        return h

    def finish(self) -> None:
        self.finished_at = _now()
        up = [h for h in self.hosts if h.is_up]
        self.stats = {
            "total_hosts": len(self.hosts),
            "hosts_up": len(up),
            "open_ports": sum(len(h.ports) for h in self.hosts),
            "with_vendor": sum(1 for h in self.hosts if h.vendor),
            "with_hostname": sum(1 for h in self.hosts if h.hostname),
        }

    def to_dict(self) -> Dict[str, Any]:
        # Hosts sorted by numeric IP so the JSON (and the report built from it) reads in order.
        def key(h: Host):
            try:
                return tuple(int(p) for p in h.ip.split("."))
            except ValueError:
                return (999, 999, 999, 999)

        self.hosts.sort(key=key)
        return {
            "tool": self.tool,
            "version": self.version,
            "scanner_host": self.scanner_host,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "networks": self.networks,
            "stats": self.stats,
            "interfaces": [i.to_dict() for i in self.interfaces],
            "hosts": [h.to_dict() for h in self.hosts],
        }
