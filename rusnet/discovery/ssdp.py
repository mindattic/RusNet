"""SSDP discovery: ask UPnP devices to describe themselves.

SSDP is the discovery half of UPnP. We send the standard M-SEARCH multicast that every media player,
smart TV, router, printer and IoT gadget is designed to answer, then collect their replies. This is
exactly how a DLNA app or a casting device finds things - the devices advertise themselves on
purpose. We read the location/server/USN headers they return; we do not fetch or act on anything.
"""

from __future__ import annotations

import socket
from typing import Dict, List
from urllib.parse import urlparse

MCAST_ADDR = "239.255.255.250"
MCAST_PORT = 1900

_MSEARCH = (
    "M-SEARCH * HTTP/1.1\r\n"
    f"HOST: {MCAST_ADDR}:{MCAST_PORT}\r\n"
    'MAN: "ssdp:discover"\r\n'
    "MX: 2\r\n"
    "ST: ssdp:all\r\n"
    "\r\n"
).encode()


def _parse_headers(text: str) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    for line in text.splitlines()[1:]:
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip().lower()] = v.strip()
    return headers


def discover(timeout: float = 3.0) -> Dict[str, Dict[str, str]]:
    """Multicast an M-SEARCH and collect replies keyed by responder IP.

    Returns {ip: {"server": ..., "location": ..., "st": ..., "usn": ...}}.
    """
    found: Dict[str, Dict[str, str]] = {}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        sock.settimeout(timeout)
        sock.sendto(_MSEARCH, (MCAST_ADDR, MCAST_PORT))
        while True:
            try:
                data, addr = sock.recvfrom(2048)
            except socket.timeout:
                break
            ip = addr[0]
            headers = _parse_headers(data.decode("latin-1", "replace"))
            entry = found.setdefault(ip, {})
            if headers.get("server") and "server" not in entry:
                entry["server"] = headers["server"]
            loc = headers.get("location", "")
            if loc:
                entry.setdefault("location", loc)
                host = urlparse(loc).hostname
                if host:
                    entry.setdefault("location_host", host)
            if headers.get("st"):
                sts = entry.setdefault("st", "")
                if headers["st"] not in sts:
                    entry["st"] = (sts + "; " + headers["st"]).strip("; ")
            if headers.get("usn") and "usn" not in entry:
                entry["usn"] = headers["usn"]
    except OSError:
        pass
    finally:
        sock.close()
    return found
