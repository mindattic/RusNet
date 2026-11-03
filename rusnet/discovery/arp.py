"""Read the OS ARP cache: IP -> MAC pairs the machine already knows about.

A ping sweep populates this cache, so running the sweep first and then reading ARP gives a MAC for
most reachable hosts without any extra traffic. Pure read of a local table - no packets sent here.
"""

from __future__ import annotations

import ipaddress
import re
import subprocess
import sys
from typing import Dict

# "192.168.1.1   00-11-22-33-44-55   dynamic"  (Windows)
#  or "? (192.168.1.1) at 00:11:22:33:44:55 [ether] on eth0" (Unix)
_WIN = re.compile(r"(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F]{2}(?:[-:][0-9a-fA-F]{2}){5})")
#  macOS/BSD drop leading zeros ("at 0:11:22:3:44:55"), so octets there are one or two digits.
_NIX = re.compile(r"\((\d+\.\d+\.\d+\.\d+)\)\s+at\s+([0-9a-fA-F]{1,2}(?::[0-9a-fA-F]{1,2}){5})")


def _normalise(mac: str) -> str:
    return ":".join(o.zfill(2) for o in mac.replace("-", ":").lower().split(":"))


def _keep(ip: str, mac: str) -> bool:
    """Drop broadcast / multicast / incomplete entries.

    Broadcast is recognised by its ff:ff:ff:ff:ff:ff MAC, not by a ".255" last octet: in a /23 or
    wider subnet x.x.x.255 is an ordinary host address.
    """
    if mac in ("ff:ff:ff:ff:ff:ff", "00:00:00:00:00:00"):
        return False
    try:
        return not ipaddress.ip_address(ip).is_multicast
    except ValueError:
        return False


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
        if _keep(ip, mac):
            pairs[ip] = mac
    # The Unix regex can miss some rows; try the Windows one as a fallback and vice-versa.
    if not pairs:
        for match in _WIN.finditer(out):
            ip, mac = match.group(1), _normalise(match.group(2))
            if _keep(ip, mac):
                pairs[ip] = mac
    return pairs
