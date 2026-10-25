"""Light TCP service probe: which well-known service ports a host has open.

This is a plain TCP connect (the OS three-way handshake, same as any client opening a connection) to
a short, curated list of common service ports, used only to label a device - "this one speaks HTTP
and SMB, probably a NAS". It is not a full port scan and does not attempt to authenticate or exploit
anything. For a host that answers HTTP, we read the `Server:` header; otherwise we take whatever
greeting banner the service volunteers in the first moment. Scope it to hosts on your own network.
"""

from __future__ import annotations

import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List

from ..model import Port

# Ports worth checking to identify a device, with the service usually behind each.
COMMON_PORTS: Dict[int, str] = {
    21: "FTP",
    22: "SSH",
    23: "Telnet",
    25: "SMTP",
    53: "DNS",
    80: "HTTP",
    110: "POP3",
    111: "RPC",
    135: "MSRPC",
    139: "NetBIOS",
    143: "IMAP",
    443: "HTTPS",
    445: "SMB",
    515: "LPD (printer)",
    548: "AFP",
    554: "RTSP",
    631: "IPP (printer)",
    993: "IMAPS",
    995: "POP3S",
    1433: "MSSQL",
    1723: "PPTP",
    1883: "MQTT",
    2049: "NFS",
    3000: "HTTP-alt",
    3306: "MySQL",
    3389: "RDP",
    5000: "UPnP/HTTP",
    5432: "PostgreSQL",
    5900: "VNC",
    6379: "Redis",
    7070: "RTSP-alt",
    8008: "HTTP-alt",
    8080: "HTTP-proxy",
    8443: "HTTPS-alt",
    8883: "MQTT-TLS",
    9000: "HTTP-alt",
    9100: "RAW print (JetDirect)",
    32400: "Plex",
    49152: "UPnP",
}

# A reasonable default subset so a full scan stays quick; callers can pass the whole map.
DEFAULT_PORTS: List[int] = [
    21, 22, 23, 53, 80, 139, 443, 445, 515, 554, 631, 1883, 3389, 5000, 8080, 8443, 9100, 32400,
]


def _grab_banner(sock: socket.socket, port: int) -> str:
    """Read a small, safe banner from an already-open socket, if the service offers one."""
    try:
        sock.settimeout(1.0)
        if port in (80, 8080, 8008, 3000, 5000, 9000):
            host_line = "Host: scan\r\n"
            sock.sendall(("HEAD / HTTP/1.0\r\n" + host_line + "\r\n").encode())
            data = sock.recv(512).decode("latin-1", "replace")
            for line in data.splitlines():
                if line.lower().startswith("server:"):
                    return line.split(":", 1)[1].strip()
            first = data.splitlines()[0] if data.splitlines() else ""
            return first.strip()[:120]
        # Many plaintext services greet on connect (SSH, FTP, SMTP, Telnet, Redis...).
        data = sock.recv(256)
        return data.decode("latin-1", "replace").strip().splitlines()[0][:120] if data else ""
    except OSError:
        return ""
    except IndexError:
        return ""


def _probe(ip: str, port: int, timeout: float) -> Port | None:
    try:
        with socket.create_connection((ip, port), timeout=timeout) as sock:
            banner = _grab_banner(sock, port)
            return Port(number=port, service=COMMON_PORTS.get(port, ""), banner=banner)
    except (OSError, socket.timeout):
        return None


def scan_host(ip: str, ports: List[int], timeout: float = 0.6, workers: int = 32) -> List[Port]:
    """Return the open ports found on one host."""
    found: List[Port] = []
    with ThreadPoolExecutor(max_workers=min(workers, len(ports) or 1)) as pool:
        futures = [pool.submit(_probe, ip, p, timeout) for p in ports]
        for fut in as_completed(futures):
            res = fut.result()
            if res is not None:
                found.append(res)
    found.sort(key=lambda p: p.number)
    return found
