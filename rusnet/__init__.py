"""RusNet - a local-network inventory scanner.

RusNet maps the network you administer: it enumerates your own machine's interfaces, discovers the
hosts on your local subnet (ping sweep + ARP neighbours + device self-advertisements), identifies
each one as far as the device itself reveals (hostname, MAC vendor, advertised model, common open
service ports), and writes the result to a JSON file and a self-contained interactive HTML report.

It is a home/office network-inventory tool in the spirit of Fing or Angry IP Scanner: standard
discovery techniques, local scope, no exploitation. Only scan networks you own or are authorised to.
"""

__version__ = "0.1.0"
