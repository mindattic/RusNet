"""Discovery modules - each learns one kind of fact about the local network.

Every module is passive or uses only standard, benign network operations (ARP table reads, ICMP
echo, reverse DNS, TCP connect to well-known service ports, and listening for the device
advertisements SSDP/mDNS broadcast by design). Nothing here attempts authentication or exploitation.
"""
