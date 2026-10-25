"""Infer a device type and a coarse OS guess from everything a host revealed.

Nothing here touches the network - it reasons purely over the facts already collected (vendor, open
ports, reply TTL, SSDP/mDNS advertisements, hostname) to label a host as a router, printer, NAS,
camera, phone, media device, PC, or IoT gadget. These are heuristics, so they are labelled as
guesses in the report.
"""

from __future__ import annotations

from typing import List

from .model import Host


def _port_set(host: Host) -> set[int]:
    return {p.number for p in host.ports}


def _text_blob(host: Host) -> str:
    parts: List[str] = [host.hostname, host.vendor, host.model]
    for p in host.ports:
        parts.append(p.banner)
    for v in host.details.values():
        if isinstance(v, str):
            parts.append(v)
        elif isinstance(v, (list, tuple)):
            parts.extend(str(x) for x in v)
    return " ".join(parts).lower()


def os_from_ttl(ttl: int | None) -> str:
    if ttl is None:
        return ""
    if ttl <= 64:
        return "Linux/Unix/Android"
    if ttl <= 128:
        return "Windows"
    return "Network appliance"


def classify(host: Host) -> None:
    """Fill host.device_type, host.os_guess and, when clear, host.model (in place)."""
    ports = _port_set(host)
    blob = _text_blob(host)

    if not host.os_guess:
        host.os_guess = os_from_ttl(host.ttl)

    # Pull a model name out of an SSDP server string or mDNS service when obvious.
    if not host.model:
        server = str(host.details.get("ssdp_server", ""))
        if server:
            host.model = server.split("UPnP")[0].strip(" ,/")[:80]

    def has(*words: str) -> bool:
        return any(w in blob for w in words)

    # Order matters: the most specific signals win.
    if host.is_gateway or has("router", "gateway", "fritz!box", "openwrt", "dd-wrt") or (
        {53, 80}.issubset(ports) and host.is_gateway
    ):
        host.device_type = "Router / gateway"
    elif has("espressif", "esp32", "esp8266", "tuya", "sonoff", "tasmota") or 1883 in ports:
        host.device_type = "IoT / smart-home device"
    elif has("hue", "lifx", "nanoleaf", "smart bulb"):
        host.device_type = "Smart lighting"
    elif ports & {515, 631, 9100} or has("printer", "jetdirect", "lexmark", "brother", "epson", "canon", "laserjet", "officejet"):
        host.device_type = "Printer"
    elif ports & {554, 7070} or has("camera", "ipcam", "hikvision", "dahua", "rtsp", "nvr"):
        host.device_type = "IP camera / NVR"
    elif ports & {32400} or has("plex", "dlna", "mediaserver", "jellyfin", "emby"):
        host.device_type = "Media server"
    elif has("roku", "chromecast", "appletv", "firetv", "shield", "smart tv", "bravia", "samsung tv", "lg tv", "webos", "tizen"):
        host.device_type = "TV / streaming device"
    elif has("sonos", "airplay", "spotify", "speaker", "echo", "alexa", "homepod"):
        host.device_type = "Smart speaker / audio"
    elif has("synology", "qnap", "nas", "truenas", "freenas", "diskstation", "readynas", "unraid") or (
        # NFS/AFP are real file-server signals; bare SMB (445/139) is on every Windows box, so it
        # alone doesn't make a NAS - require an NFS/AFP port or an explicitly shared (non-Windows) SMB.
        ports & {2049, 548}
        or (445 in ports and not host.os_guess.startswith("Windows"))
    ):
        host.device_type = "NAS / file server"
    elif has("iphone", "ipad", "android", "pixel", "galaxy", "oneplus", "xiaomi") or (
        host.vendor in ("Apple", "Samsung") and 62078 in ports
    ):
        host.device_type = "Phone / tablet"
    elif host.vendor in ("Raspberry Pi Foundation", "Raspberry Pi Trading"):
        host.device_type = "Single-board computer (Raspberry Pi)"
    elif ports & {3389} or (host.os_guess == "Windows" and ports & {445, 135, 139}):
        host.device_type = "Windows PC"
    elif ports & {22} and host.os_guess.startswith("Linux"):
        host.device_type = "Linux host / server"
    elif host.vendor in ("Apple",):
        host.device_type = "Apple device"
    elif host.vendor and ("vmware" in host.vendor.lower() or "virtualbox" in blob or "qemu" in blob):
        host.device_type = "Virtual machine"
    elif ports:
        host.device_type = "Host with network services"
    else:
        host.device_type = "Unknown device"
