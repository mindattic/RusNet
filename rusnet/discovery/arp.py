"""Read the OS ARP cache: IP -> MAC pairs the machine already knows about.

A ping sweep populates this cache, so running the sweep first and then reading ARP gives a MAC for
most reachable hosts without any extra traffic. Pure read of a local table - no packets sent here.
"""

from __future__ import annotations

import re
import subprocess
import sys
from typing import Dict

# "192.168.1.1   00-11-22-33-44-55   dynamic"  (Windows)
#  or "? (192.168.1.1) at 00:11:22:33:44:55 [ether] on eth0" (Unix)
_WIN = re.compile(r"(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F]{2}(?:[-:][0-9a-fA-F]{2}){5})")
_NIX = re.compile(r"\((\d+\.\d+\.\d+\.\d+)\)\s+at\s+([0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5})")


def _normalise(mac: str) -> str:
    return mac.replace("-", ":").lower()


def read_table() -> Dict[str, str]:
    """Return {ip: mac} from the OS ARP cache. Empty dict if the command is unavailable."""
    pairs: Dict[str, str] = {}
    try:
        out = subprocess.check_output(["arp", "-a"], text=True, errors="replace")
    except Exception:
        return pairs

    regex = _WIN if sys.platform.startswith("win") else _NIX
    for match in regex.finditer(out):
        ip, mac = match.group(1), _normalise(match.group(2))
        # Skip broadcast / multicast / incomplete entries.
        if mac in ("ff:ff:ff:ff:ff:ff", "00:00:00:00:00:00"):
            continue
        if ip.endswith(".255") or ip.startswith("224.") or ip.startswith("239."):
            continue
        pairs[ip] = mac
    # The Unix regex can miss some rows; try the Windows one as a fallback and vice-versa.
    if not pairs:
        for match in _WIN.finditer(out):
            pairs[match.group(1)] = _normalise(match.group(2))
    return pairs
