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
    # psutil can't give gateways/DNS; discover() fills those from the OS tool afterwards by CIDR.
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


_IPV4 = re.compile(r"^\d+\.\d+\.\d+\.\d+$")


def _is_address(text: str) -> bool:
    """True for a bare IPv4/IPv6 address (an IPv6 zone suffix like "%12" is allowed)."""
    try:
        ipaddress.ip_address(text.split("%", 1)[0])
        return True
    except ValueError:
        return False


def _parse_ipconfig(text: str) -> List[Interface]:
    """Parse Windows `ipconfig /all` output into interfaces."""
    out: List[Interface] = []
    current: Interface | None = None
    # Which multi-valued field a bare continuation line belongs to ("dns" / "gateway" / None).
    # ipconfig lists IPv6 values first, so the IPv4 gateway or DNS server is often on a later line.
    pending: str | None = None
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
            pending = None
            continue
        if current is None:
            continue
        stripped = line.strip()
        if _is_address(stripped):
            # Continuation line: another value of the previous field (extra DNS server, or the
            # IPv4 gateway listed under an IPv6 one). An IPv6 value has colons, so test this
            # before the "label : value" match, which would misread it as a new field.
            if _IPV4.match(stripped):
                if pending == "dns":
                    current.dns.append(stripped)
                elif pending == "gateway" and not current.gateway:
                    current.gateway = stripped
            continue
        m = re.match(r"(.+?)[\.\s]*:\s*(.*)$", stripped)
        if not m:
            continue
        label, value = m.group(1).strip().lower(), m.group(2).strip()
        pending = None
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
            if _IPV4.match(value):
                current.gateway = value
            pending = "gateway"
        elif "dns servers" in label:
            if _IPV4.match(value):
                current.dns.append(value)
            pending = "dns"
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
