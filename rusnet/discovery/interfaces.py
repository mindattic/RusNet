"""Enumerate the scanning machine's own network adapters.

We prefer `psutil` when it is installed (clean, cross-platform), and otherwise fall back to parsing
the OS's own tools: `ipconfig /all` on Windows, `ip`/`ifconfig` elsewhere. The goal is, per active
adapter, its IP, MAC, netmask (as a CIDR), gateway and DNS servers - enough to know which subnet(s)
to sweep.
"""

from __future__ import annotations

import ipaddress
import re
import socket
import subprocess
import sys
from typing import List

from ..model import Interface


def _cidr_from_mask(ip: str, mask: str) -> str:
    try:
        net = ipaddress.ip_network(f"{ip}/{mask}", strict=False)
        return str(net)
    except ValueError:
        return ""


def _via_psutil() -> List[Interface]:
    import psutil  # type: ignore

    out: List[Interface] = []
    addrs = psutil.net_if_addrs()
    stats = psutil.net_if_stats()
    gws = {}
    try:
        gw = psutil.net_if_stats  # placeholder; gateways need netifaces, handled below
    except Exception:
        gw = None
    for name, snics in addrs.items():
        st = stats.get(name)
        if st is not None and not st.isup:
            continue
        iface = Interface(name=name)
        for snic in snics:
            fam = snic.family
            if fam == socket.AF_INET:
                if snic.address and not snic.address.startswith("169.254"):
                    iface.ip = snic.address
                    iface.netmask = snic.netmask or ""
                    if snic.netmask:
                        iface.cidr = _cidr_from_mask(snic.address, snic.netmask)
            elif getattr(psutil, "AF_LINK", None) is not None and fam == psutil.AF_LINK:
                iface.mac = (snic.address or "").replace("-", ":").lower()
        if iface.ip and not iface.ip.startswith("127."):
            out.append(iface)
    return out


def _parse_ipconfig(text: str) -> List[Interface]:
    """Parse Windows `ipconfig /all` output into interfaces."""
    out: List[Interface] = []
    current: Interface | None = None
    pending_dns = False
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line:
            continue
        # An adapter header has no leading whitespace and ends with a colon.
        if not line.startswith(" ") and line.endswith(":"):
            if current and current.ip:
                out.append(current)
            name = re.sub(r"^.*adapter\s+", "", line[:-1], flags=re.I).strip()
            current = Interface(name=name or line[:-1].strip())
            pending_dns = False
            continue
        if current is None:
            continue
        stripped = line.strip()
        m = re.match(r"(.+?)[\.\s]*:\s*(.*)$", stripped)
        if not m:
            # Continuation line (extra DNS server, etc.).
            if pending_dns and re.match(r"^\d+\.\d+\.\d+\.\d+$", stripped):
                current.dns.append(stripped)
            continue
        label, value = m.group(1).strip().lower(), m.group(2).strip()
        pending_dns = False
        if "physical address" in label:
            current.mac = value.replace("-", ":").lower()
        elif "ipv4 address" in label:
            ip = value.replace("(Preferred)", "").replace("(Tentative)", "").strip()
            ip = re.sub(r"\(.*\)", "", ip).strip()
            if ip and not ip.startswith("169.254"):
                current.ip = ip
        elif "subnet mask" in label:
            current.netmask = value
            if current.ip:
                current.cidr = _cidr_from_mask(current.ip, value)
        elif "default gateway" in label:
            if re.match(r"^\d+\.\d+\.\d+\.\d+$", value):
                current.gateway = value
        elif "dns servers" in label:
            if re.match(r"^\d+\.\d+\.\d+\.\d+$", value):
                current.dns.append(value)
            pending_dns = True
        elif "dhcp enabled" in label:
            current.dhcp = value
    if current and current.ip:
        out.append(current)
    return out


def _via_ipconfig() -> List[Interface]:
    text = subprocess.check_output(["ipconfig", "/all"], text=True, errors="replace")
    return _parse_ipconfig(text)


def _parse_ip_addr(text: str) -> List[Interface]:
    """Parse Linux `ip -o addr` + routes (best-effort, for non-Windows hosts)."""
    out: List[Interface] = []
    by_name = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        name = parts[1]
        iface = by_name.get(name) or Interface(name=name)
        by_name[name] = iface
        if parts[2] == "inet":
            cidr = parts[3]
            iface.ip = cidr.split("/")[0]
            try:
                net = ipaddress.ip_network(cidr, strict=False)
                iface.cidr = str(net)
                iface.netmask = str(net.netmask)
            except ValueError:
                pass
    for iface in by_name.values():
        if iface.ip and not iface.ip.startswith("127.") and not iface.ip.startswith("169.254"):
            out.append(iface)
    return out


def _via_ip() -> List[Interface]:
    text = subprocess.check_output(["ip", "-o", "addr"], text=True, errors="replace")
    ifaces = _parse_ip_addr(text)
    try:
        routes = subprocess.check_output(["ip", "route"], text=True, errors="replace")
        for line in routes.splitlines():
            if line.startswith("default via"):
                gw = line.split()[2]
                dev = line.split("dev")[1].split()[0] if "dev" in line else ""
                for iface in ifaces:
                    if not dev or iface.name == dev:
                        iface.gateway = gw
    except Exception:
        pass
    return ifaces


def discover() -> List[Interface]:
    """Return the machine's active, non-loopback interfaces, by whatever method works."""
    try:
        import psutil  # noqa: F401

        ifaces = _via_psutil()
        if ifaces:
            # psutil doesn't give gateways without netifaces; fill from the OS tool.
            try:
                extra = _via_ipconfig() if sys.platform.startswith("win") else _via_ip()
                gw_by_cidr = {i.cidr: i.gateway for i in extra if i.gateway}
                dns_by_cidr = {i.cidr: i.dns for i in extra if i.dns}
                for i in ifaces:
                    if not i.gateway:
                        i.gateway = gw_by_cidr.get(i.cidr, "")
                    if not i.dns:
                        i.dns = dns_by_cidr.get(i.cidr, [])
            except Exception:
                pass
            return ifaces
    except ImportError:
        pass

    try:
        if sys.platform.startswith("win"):
            return _via_ipconfig()
        return _via_ip()
    except Exception:
        # Last resort: one interface built from the primary outbound socket.
        return [_primary_only()]


def _primary_only() -> Interface:
    iface = Interface(name="primary")
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        iface.ip = s.getsockname()[0]
        s.close()
        iface.cidr = _cidr_from_mask(iface.ip, "255.255.255.0")
        iface.netmask = "255.255.255.0"
    except OSError:
        pass
    return iface
