"""Unit tests for the RusNet core. Pure-logic coverage only - nothing here touches the network.

    python -m unittest discover -s tests        (from the repo root)
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rusnet import classify
from rusnet.cli import _load_scan
from rusnet.discovery import arp, interfaces, oui, ping, ports
from rusnet.model import Host, Interface, Port, Scan
from rusnet.report import build_html


class ModelTests(unittest.TestCase):
    def test_host_for_is_idempotent(self):
        s = Scan()
        a = s.host_for("10.0.0.1")
        b = s.host_for("10.0.0.1")
        self.assertIs(a, b)
        self.assertEqual(len(s.hosts), 1)

    def test_sources_dedup(self):
        h = Host(ip="10.0.0.1")
        h.add_source("ping")
        h.add_source("ping")
        h.add_source("arp")
        self.assertEqual(h.sources, ["ping", "arp"])

    def test_finish_and_sort(self):
        s = Scan()
        s.host_for("10.0.0.20").is_up = True
        s.host_for("10.0.0.3").is_up = True
        s.host_for("10.0.0.3").ports = [Port(80, "HTTP")]
        s.finish()
        d = s.to_dict()
        self.assertEqual([h["ip"] for h in d["hosts"]], ["10.0.0.3", "10.0.0.20"])
        self.assertEqual(d["stats"]["hosts_up"], 2)
        self.assertEqual(d["stats"]["open_ports"], 1)


class ClassifyTests(unittest.TestCase):
    def _c(self, **kw):
        ports_ = kw.pop("ports", [])
        h = Host(**kw)
        h.ports = [Port(p) for p in ports_]
        classify.classify(h)
        return h

    def test_os_from_ttl(self):
        self.assertEqual(classify.os_from_ttl(64), "Linux/Unix/Android")
        self.assertEqual(classify.os_from_ttl(128), "Windows")
        self.assertEqual(classify.os_from_ttl(255), "Network appliance")
        self.assertEqual(classify.os_from_ttl(None), "")

    def test_gateway_is_router(self):
        self.assertEqual(self._c(ip="1.1.1.1", is_gateway=True).device_type, "Router / gateway")

    def test_printer_by_port(self):
        self.assertEqual(self._c(ip="1.1.1.2", ttl=255, ports=[9100]).device_type, "Printer")

    def test_windows_pc_not_nas_on_bare_smb(self):
        # 445 on a Windows-TTL host is an ordinary PC, not a NAS.
        self.assertEqual(self._c(ip="1.1.1.3", ttl=128, ports=[445, 139, 3389]).device_type, "Windows PC")

    def test_nas_on_nfs(self):
        self.assertEqual(self._c(ip="1.1.1.4", ttl=64, ports=[2049, 445]).device_type, "NAS / file server")

    def test_raspberry_pi(self):
        h = self._c(ip="1.1.1.5", ttl=64, vendor="Raspberry Pi Foundation", ports=[22])
        self.assertIn("Raspberry Pi", h.device_type)

    def test_unknown(self):
        self.assertEqual(self._c(ip="1.1.1.6").device_type, "Unknown device")


class OuiTests(unittest.TestCase):
    def test_known_prefix(self):
        self.assertEqual(oui.lookup("b8:27:eb:11:22:33"), "Raspberry Pi Foundation")

    def test_randomised_mac(self):
        # Locally-administered bit set in the first octet (0x02).
        self.assertEqual(oui.lookup("aa:bb:cc:dd:ee:ff"), "(randomised MAC)")

    def test_unknown_prefix(self):
        self.assertEqual(oui.lookup("00:00:01:02:03:04"), "")

    def test_empty(self):
        self.assertEqual(oui.lookup(""), "")


class ArpParseTests(unittest.TestCase):
    def test_windows_rows(self):
        sample = (
            "Interface: 192.168.1.50 --- 0x5\n"
            "  Internet Address      Physical Address      Type\n"
            "  192.168.1.1           f8-1a-67-11-22-33     dynamic\n"
            "  192.168.1.255         ff-ff-ff-ff-ff-ff     static\n"
            "  224.0.0.22            01-00-5e-00-00-16     static\n"
        )
        pairs = {}
        for m in arp._WIN.finditer(sample):
            ip, mac = m.group(1), m.group(2).replace("-", ":").lower()
            if mac == "ff:ff:ff:ff:ff:ff" or ip.endswith(".255") or ip.startswith("224."):
                continue
            pairs[ip] = mac
        self.assertEqual(pairs, {"192.168.1.1": "f8:1a:67:11:22:33"})


class InterfaceParseTests(unittest.TestCase):
    def test_parse_ipconfig(self):
        sample = (
            "Windows IP Configuration\n\n"
            "Wireless LAN adapter Wi-Fi:\n\n"
            "   Physical Address. . . . . . . . . : AA-BB-CC-DD-EE-FF\n"
            "   DHCP Enabled. . . . . . . . . . . : Yes\n"
            "   IPv4 Address. . . . . . . . . . . : 192.168.1.50(Preferred)\n"
            "   Subnet Mask . . . . . . . . . . . : 255.255.255.0\n"
            "   Default Gateway . . . . . . . . . : 192.168.1.1\n"
            "   DNS Servers . . . . . . . . . . . : 1.1.1.1\n"
            "                                       8.8.8.8\n"
        )
        ifaces = interfaces._parse_ipconfig(sample)
        self.assertEqual(len(ifaces), 1)
        i = ifaces[0]
        self.assertEqual(i.ip, "192.168.1.50")
        self.assertEqual(i.mac, "aa:bb:cc:dd:ee:ff")
        self.assertEqual(i.gateway, "192.168.1.1")
        self.assertEqual(i.cidr, "192.168.1.0/24")
        self.assertIn("1.1.1.1", i.dns)
        self.assertIn("8.8.8.8", i.dns)


class PingTargetTests(unittest.TestCase):
    def test_hosts_for_24(self):
        self.assertEqual(len(ping.hosts_for("192.168.1.0/24")), 254)

    def test_cap(self):
        # A /16 is 65534 hosts; the cap must bound it.
        self.assertEqual(len(ping.hosts_for("10.0.0.0/16", max_hosts=100)), 100)

    def test_bad_cidr(self):
        self.assertEqual(ping.hosts_for("not-a-cidr"), [])


class PortsTests(unittest.TestCase):
    def test_common_map_has_services(self):
        self.assertEqual(ports.COMMON_PORTS[80], "HTTP")
        self.assertEqual(ports.COMMON_PORTS[9100], "RAW print (JetDirect)")
        self.assertTrue(set(ports.DEFAULT_PORTS).issubset(set(ports.COMMON_PORTS)))


class ReportTests(unittest.TestCase):
    def _scan(self):
        s = Scan()
        s.networks = ["192.168.1.0/24"]
        h = Host(ip="192.168.1.1", is_gateway=True, is_up=True, ttl=64, hostname="router")
        h.ports = [Port(80, "HTTP", "nginx")]
        classify.classify(h)
        s.hosts.append(h)
        s.finish()
        return s

    def test_viewer_shell(self):
        html = build_html(None)
        self.assertIn("rusnet.load", html)
        self.assertIn("ma-theme-toggle", html)
        self.assertNotIn("__RUSNET_DATA__ =", html)  # dataless shell

    def test_embedded_report(self):
        html = build_html(self._scan())
        self.assertIn("__RUSNET_DATA__ =", html)
        self.assertIn("192.168.1.1", html)

    def test_script_breakout_is_escaped(self):
        # Only a literal </script> can terminate the data block and break out; it must be neutralised.
        s = self._scan()
        s.hosts[0].ports[0].banner = "</script><script>evil()</script>"
        html = build_html(s)
        self.assertNotIn("</script><script>evil()", html)
        self.assertIn(r"<\/script>", html)

    def test_json_round_trip(self):
        import tempfile
        s = self._scan()
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
            json.dump(s.to_dict(), fh)
            path = fh.name
        try:
            s2 = _load_scan(path)
            self.assertEqual(len(s2.hosts), 1)
            self.assertEqual(s2.hosts[0].device_type, "Router / gateway")
            self.assertEqual(s2.hosts[0].ports[0].service, "HTTP")
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
