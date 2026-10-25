"""Resolve names for discovered hosts.

Reverse DNS (PTR) via the resolver, plus a NetBIOS name query on Windows (`nbtstat -A`) which often
names a machine that has no PTR record. Both are standard name lookups.
"""

from __future__ import annotations

import re
import socket
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List


def _reverse(ip: str) -> str:
    try:
        name, _, _ = socket.gethostbyaddr(ip)
        return name
    except (socket.herror, socket.gaierror, OSError):
        return ""


def _netbios(ip: str) -> str:
    if not sys.platform.startswith("win"):
        return ""
    try:
        out = subprocess.run(
            ["nbtstat", "-A", ip],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            errors="replace",
            timeout=4,
        ).stdout or ""
    except Exception:
        return ""
    # The <00> UNIQUE record is the machine name.
    for line in out.splitlines():
        m = re.match(r"\s*([^\s]+)\s+<00>\s+UNIQUE", line)
        if m:
            name = m.group(1).strip()
            if name and name != "__MSBROWSE__":
                return name
    return ""


def resolve_all(ips: List[str], workers: int = 64) -> Dict[str, str]:
    """Best-effort name per IP (PTR first, then NetBIOS). Missing names are omitted."""
    names: Dict[str, str] = {}

    def work(ip: str) -> tuple[str, str]:
        name = _reverse(ip)
        if not name:
            name = _netbios(ip)
        return ip, name

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for fut in as_completed([pool.submit(work, ip) for ip in ips]):
            ip, name = fut.result()
            if name:
                names[ip] = name
    return names
