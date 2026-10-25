"""Ping sweep: find which addresses on a subnet answer ICMP echo.

Uses the OS `ping` binary (one echo, short timeout) over a thread pool, so no raw sockets or admin
rights are needed. Returns, per responding IP, its round-trip time and the reply TTL (a coarse OS
hint: ~64 Linux/Android, ~128 Windows, ~255 many network appliances).
"""

from __future__ import annotations

import ipaddress
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

_TTL = re.compile(r"ttl[=|:](\d+)", re.I)
_TIME = re.compile(r"time[=<]([\d.]+)\s*ms", re.I)


@dataclass
class PingResult:
    ip: str
    is_up: bool
    rtt_ms: Optional[float] = None
    ttl: Optional[int] = None


def _ping_once(ip: str, timeout_ms: int) -> PingResult:
    if sys.platform.startswith("win"):
        cmd = ["ping", "-n", "1", "-w", str(timeout_ms), ip]
    else:
        # -W is seconds on Linux; round up to at least 1.
        secs = max(1, round(timeout_ms / 1000))
        cmd = ["ping", "-c", "1", "-W", str(secs), ip]
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            errors="replace",
            timeout=max(2, timeout_ms / 1000 + 1),
        )
    except Exception:
        return PingResult(ip=ip, is_up=False)

    out = proc.stdout or ""
    # Windows returns 0 even for "Destination host unreachable", so check the text too.
    up = proc.returncode == 0 and "ttl" in out.lower() and "unreachable" not in out.lower()
    if not up:
        return PingResult(ip=ip, is_up=False)
    ttl_m = _TTL.search(out)
    time_m = _TIME.search(out)
    return PingResult(
        ip=ip,
        is_up=True,
        rtt_ms=float(time_m.group(1)) if time_m else None,
        ttl=int(ttl_m.group(1)) if ttl_m else None,
    )


def hosts_for(cidr: str, max_hosts: int = 1024) -> List[str]:
    """Usable host addresses in a CIDR, capped so a stray /8 can't launch a million pings."""
    try:
        net = ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return []
    if net.num_addresses > max_hosts + 2:
        # Too large to sweep in full; limit to the first chunk and let the caller warn.
        return [str(h) for i, h in enumerate(net.hosts()) if i < max_hosts]
    return [str(h) for h in net.hosts()]


def sweep(
    cidr: str,
    timeout_ms: int = 800,
    workers: int = 128,
    max_hosts: int = 1024,
    on_progress: Optional[Callable[[int, int], None]] = None,
) -> Dict[str, PingResult]:
    """Ping every host in the CIDR concurrently; return {ip: PingResult} for the ones that answer."""
    targets = hosts_for(cidr, max_hosts=max_hosts)
    results: Dict[str, PingResult] = {}
    done = 0
    total = len(targets)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_ping_once, ip, timeout_ms): ip for ip in targets}
        for fut in as_completed(futures):
            res = fut.result()
            done += 1
            if on_progress:
                on_progress(done, total)
            if res.is_up:
                results[res.ip] = res
    return results
