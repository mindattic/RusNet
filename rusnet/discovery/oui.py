"""MAC -> vendor lookup from the IEEE OUI (first three octets).

A small, offline prefix table ships with RusNet (`rusnet/data/oui.csv`) covering the vendors most
common on a home/office LAN. If the full IEEE registry is present at `rusnet/data/oui-full.txt`
(the user can drop the official `oui.txt` there), it is loaded too and takes precedence. No network
call - this is a static lookup.
"""

from __future__ import annotations

import csv
import os
import re
from functools import lru_cache
from typing import Dict

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


def _prefix(mac: str) -> str:
    hexonly = re.sub(r"[^0-9a-fA-F]", "", mac).upper()
    return hexonly[:6]


@lru_cache(maxsize=1)
def _table() -> Dict[str, str]:
    table: Dict[str, str] = {}
    csv_path = os.path.join(_DATA_DIR, "oui.csv")
    if os.path.exists(csv_path):
        with open(csv_path, newline="", encoding="utf-8") as fh:
            for row in csv.reader(fh):
                if len(row) >= 2 and not row[0].startswith("#"):
                    table[_prefix(row[0])] = row[1].strip()

    # Optional full IEEE registry (oui.txt format: "001122     (base 16)   Vendor Name").
    full_path = os.path.join(_DATA_DIR, "oui-full.txt")
    if os.path.exists(full_path):
        with open(full_path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                m = re.match(r"\s*([0-9A-Fa-f]{6})\s+\(base 16\)\s+(.+)", line)
                if m:
                    table[m.group(1).upper()] = m.group(2).strip()
    return table


def lookup(mac: str) -> str:
    """Return the vendor name for a MAC, or '' if the prefix is unknown.

    A locally-administered / randomised MAC (the 2nd-least-significant bit of the first octet set)
    is reported as such, since it deliberately hides the real vendor.
    """
    if not mac:
        return ""
    prefix = _prefix(mac)
    if len(prefix) < 6:
        return ""
    try:
        first_octet = int(prefix[:2], 16)
        if first_octet & 0x02:
            return "(randomised MAC)"
    except ValueError:
        pass
    return _table().get(prefix, "")
