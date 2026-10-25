"""mDNS / DNS-SD discovery: catch the service announcements Apple/Bonjour-style devices broadcast.

We send one standard multicast DNS query for the service-enumeration name
`_services._dns-sd._udp.local` and listen briefly for answers. Printers, Chromecasts, HomeKit
gadgets, NAS boxes and Macs all advertise their services this way by design. We parse the PTR answers
to learn which service types exist and which IPs host them. Pure listen-and-parse; nothing is probed.
"""

from __future__ import annotations

import socket
import struct
from typing import Dict, List

MCAST_ADDR = "224.0.0.251"
MCAST_PORT = 5353


def _encode_name(name: str) -> bytes:
    out = b""
    for label in name.split("."):
        if label:
            out += bytes([len(label)]) + label.encode()
    return out + b"\x00"


def _build_query(name: str, qtype: int = 12) -> bytes:
    # Header: id=0, flags=0 (standard query), 1 question.
    header = struct.pack(">HHHHHH", 0, 0, 1, 0, 0, 0)
    # qclass: IN (1) with the top "unicast-response" (QU) bit set -> 0x8001. Without it, responders
    # answer by multicast to 224.0.0.251:5353, which this ephemeral, non-group-joined socket never
    # receives; with it they unicast the reply back to our source port, so discovery actually works.
    question = _encode_name(name) + struct.pack(">HH", qtype, 0x8001)
    return header + question


def _read_name(data: bytes, offset: int) -> tuple[str, int]:
    """Decode a DNS name, following compression pointers; return (name, next_offset)."""
    labels: List[str] = []
    jumped = False
    next_offset = offset
    guard = 0
    while guard < 128:
        guard += 1
        if offset >= len(data):
            break
        length = data[offset]
        if length == 0:
            offset += 1
            if not jumped:
                next_offset = offset
            break
        if length & 0xC0 == 0xC0:
            pointer = ((length & 0x3F) << 8) | data[offset + 1]
            if not jumped:
                next_offset = offset + 2
            offset = pointer
            jumped = True
            continue
        labels.append(data[offset + 1 : offset + 1 + length].decode("latin-1", "replace"))
        offset += 1 + length
    return ".".join(labels), next_offset


def discover(timeout: float = 3.0) -> Dict[str, Dict[str, List[str]]]:
    """Return {ip: {"services": [...], "names": [...]}} gathered from mDNS answers."""
    found: Dict[str, Dict[str, List[str]]] = {}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        sock.settimeout(timeout)
        query = _build_query("_services._dns-sd._udp.local")
        sock.sendto(query, (MCAST_ADDR, MCAST_PORT))
        while True:
            try:
                data, addr = sock.recvfrom(4096)
            except socket.timeout:
                break
            ip = addr[0]
            entry = found.setdefault(ip, {"services": [], "names": []})
            try:
                _parse_answers(data, entry)
            except Exception:
                # Malformed packet from a chatty device - skip it, keep listening.
                continue
    except OSError:
        pass
    finally:
        sock.close()
    # Drop empties.
    return {ip: e for ip, e in found.items() if e["services"] or e["names"]}


def _parse_answers(data: bytes, entry: Dict[str, List[str]]) -> None:
    if len(data) < 12:
        return
    _id, _flags, qd, an, ns, ar = struct.unpack(">HHHHHH", data[:12])
    offset = 12
    for _ in range(qd):
        _name, offset = _read_name(data, offset)
        offset += 4  # qtype + qclass
    for _ in range(an + ns + ar):
        name, offset = _read_name(data, offset)
        if offset + 10 > len(data):
            return
        rtype, _rclass, _ttl, rdlen = struct.unpack(">HHIH", data[offset : offset + 10])
        offset += 10
        rdata_start = offset
        if rtype == 12:  # PTR -> a service instance or type name
            target, _ = _read_name(data, rdata_start)
            if target and target not in entry["services"]:
                entry["services"].append(target)
        elif rtype in (1,) and rdlen == 4:  # A record -> a friendly name
            if name and name not in entry["names"]:
                entry["names"].append(name.rstrip("."))
        offset = rdata_start + rdlen
