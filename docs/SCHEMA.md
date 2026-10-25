# RusNet report format (schema v1)

Every RusNet scan is written to a single JSON document. This is the standardized interchange format:
any RusNet viewer (the self-contained HTML report, the Python desktop app, the .NET WebView2 app)
loads any file in this shape and renders the full interactive report from it. Hand-written or
third-party JSON renders too, as long as it matches the shape below.

The HTML report embeds one of these objects as `window.__RUSNET_DATA__`; the viewers also accept one
at runtime through `window.rusnet.load(objectOrJsonString)`.

## Top level

```jsonc
{
  "tool": "RusNet",               // producer name
  "version": "0.1.0",             // producer version
  "scanner_host": "my-pc",        // hostname of the machine that ran the scan
  "started_at":  "2026-10-25T14:03:11-05:00",   // ISO-8601 with offset
  "finished_at": "2026-10-25T14:04:48-05:00",
  "networks": ["192.168.1.0/24"], // CIDRs that were swept
  "stats": {                      // derived totals (the viewer recomputes these, so they're advisory)
    "total_hosts": 12,
    "hosts_up": 11,
    "open_ports": 34,
    "with_vendor": 9,
    "with_hostname": 7
  },
  "interfaces": [ Interface, ... ],
  "hosts":      [ Host, ... ]      // the only required non-trivial array
}
```

The viewer needs only `hosts` (an array) to render; everything else degrades gracefully.

## Interface

One of the scanning machine's own adapters.

| Field | Type | Meaning |
|---|---|---|
| `name` | string | Adapter name |
| `ip` | string | IPv4 address |
| `mac` | string | MAC, lower-case colon form |
| `netmask` | string | Dotted netmask |
| `cidr` | string | Network in CIDR form |
| `gateway` | string | Default gateway IP |
| `dns` | string[] | DNS server IPs |
| `dhcp` | string | Whether DHCP is enabled (as the OS reports it) |

## Host

One discovered device. Only `ip` is required; every other field may be absent or empty.

| Field | Type | Meaning |
|---|---|---|
| `ip` | string | **Required.** IPv4 address |
| `mac` | string | MAC address (lower-case colon form) |
| `vendor` | string | MAC OUI vendor, or `"(randomised MAC)"` for a locally-administered MAC |
| `hostname` | string | PTR / NetBIOS / mDNS name |
| `sources` | string[] | How it was seen: any of `ping`, `arp`, `ssdp`, `mdns`, `self` |
| `is_up` | bool | Responded to discovery |
| `is_self` | bool | This is the scanning machine |
| `is_gateway` | bool | This is a default gateway |
| `rtt_ms` | number\|null | Ping round-trip in ms |
| `ttl` | number\|null | Reply TTL (OS hint: ~64 Linux/Android, ~128 Windows, ~255 appliance) |
| `os_guess` | string | Coarse OS guess from TTL |
| `device_type` | string | One of the taxonomy values below (the viewer colours/groups by this) |
| `model` | string | Model string when a protocol revealed one |
| `ports` | Port[] | Open TCP service ports |
| `details` | object | Free-form extras (SSDP/mDNS fields, etc.); string or string[] values |

### Port

| Field | Type | Meaning |
|---|---|---|
| `number` | number | TCP port |
| `service` | string | Expected service name |
| `banner` | string | Short banner / `Server:` header, if offered |

## `device_type` taxonomy

The viewer has a stable colour and glyph for each of these; an unknown value falls back to the
"Unknown device" style, so new types still render.

`Router / gateway`, `Printer`, `IP camera / NVR`, `NAS / file server`, `Media server`,
`TV / streaming device`, `Smart speaker / audio`, `Smart lighting`, `IoT / smart-home device`,
`Phone / tablet`, `Windows PC`, `Linux host / server`, `Apple device`,
`Single-board computer (Raspberry Pi)`, `Virtual machine`, `Host with network services`,
`Unknown device`.

## Minimal valid example

```json
{
  "tool": "RusNet",
  "hosts": [
    { "ip": "192.168.1.1", "hostname": "router.lan", "device_type": "Router / gateway",
      "is_gateway": true, "is_up": true, "ports": [{ "number": 80, "service": "HTTP" }] },
    { "ip": "192.168.1.42", "device_type": "Unknown device", "is_up": true }
  ]
}
```

Save that as `anything.json`, open it in any RusNet viewer, and it renders.
