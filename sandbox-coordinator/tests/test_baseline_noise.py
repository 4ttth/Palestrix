"""Baseline suppression.

A Windows guest on an isolated bridge talks constantly without being asked
to. Before this was suppressed, that chatter was the only traffic most
captures held, and it scored: mDNS announcing the VM's own hostname read as
a DNS lookup (+20, T1071.004) and port 5353 read as a non-standard port
(+20, T1571). Every sample therefore floored at 40 and landed on
"suspicious", with the score varying only by whether the static packed bit
added its 15.

The packets rebuilt here are the ones actually observed in run sbx-d6630edd,
a 228-second detonation of a GUI installer that did nothing at all.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coordinator.pcapparse import (  # noqa: E402
    is_baseline_dst,
    is_baseline_name,
    parse,
)
from coordinator.verdict import assess  # noqa: E402

scapy_all = pytest.importorskip("scapy.all", reason="pcap parsing needs scapy")


def _write(path, packets):
    scapy_all.wrpcap(str(path), packets)
    return str(path)


def _mdns_hostname_announce():
    """Exactly what the npcap run captured."""
    return (
        scapy_all.Ether()
        / scapy_all.IP(src="169.254.11.5", dst="224.0.0.251")
        / scapy_all.UDP(sport=5353, dport=5353)
        / scapy_all.DNS(qd=scapy_all.DNSQR(qname="SBX-WIN10.local"))
    )


def _chatter():
    return [
        _mdns_hostname_announce(),
        # LLMNR
        scapy_all.Ether()
        / scapy_all.IP(src="169.254.11.5", dst="224.0.0.252")
        / scapy_all.UDP(sport=5355, dport=5355)
        / scapy_all.DNS(qd=scapy_all.DNSQR(qname="SBX-WIN10")),
        # SSDP
        scapy_all.Ether()
        / scapy_all.IP(src="169.254.11.5", dst="239.255.255.250")
        / scapy_all.UDP(sport=49152, dport=1900)
        / scapy_all.Raw(load=b"M-SEARCH * HTTP/1.1\r\nHOST:239.255.255.250:1900\r\n\r\n"),
        # DHCP discover
        scapy_all.Ether()
        / scapy_all.IP(src="0.0.0.0", dst="255.255.255.255")
        / scapy_all.UDP(sport=68, dport=67)
        / scapy_all.Raw(load=b"\x01\x01\x06\x00"),
        # NetBIOS name service
        scapy_all.Ether()
        / scapy_all.IP(src="169.254.11.5", dst="169.254.255.255")
        / scapy_all.UDP(sport=137, dport=137)
        / scapy_all.Raw(load=b"\x00\x00\x01\x10"),
    ]


# -- classification ------------------------------------------------------------


def test_discovery_destinations_are_baseline():
    for ip in ("224.0.0.251", "224.0.0.252", "239.255.255.250",
               "255.255.255.255", "169.254.11.5", "127.0.0.1", "0.0.0.0"):
        assert is_baseline_dst(ip), ip


def test_routable_destinations_are_not_baseline():
    for ip in ("203.0.113.10", "192.0.2.5", "8.8.8.8", "10.0.10.1"):
        assert not is_baseline_dst(ip), ip


def test_link_local_names_are_baseline():
    assert is_baseline_name("SBX-WIN10.local")
    assert is_baseline_name("SBX-WIN10")            # single label
    assert is_baseline_name("1.0.0.127.in-addr.arpa")
    assert not is_baseline_name("c2.example.com")


# -- the regression -----------------------------------------------------------


def test_pure_guest_chatter_yields_no_findings(tmp_path):
    net, events = parse(_write(tmp_path / "noise.pcap", _chatter()))

    assert net.dns_queries == 0, "the VM naming itself is not a DNS lookup"
    assert net.domains == []
    assert net.ports == []
    assert net.ips == []
    assert net.packets == 0
    assert net.baseline == len(_chatter())

    assert not any(e["level"] == "alert" for e in events)
    assert any("suppressed" in e["msg"] for e in events)


def test_the_npcap_run_no_longer_reads_suspicious(tmp_path):
    """End to end on the real numbers: packed installer + chatter only.

    Was 55/suspicious (15 packed + 20 phantom DNS + 20 phantom odd port).
    """
    net, _ = parse(_write(tmp_path / "npcap.pcap", _chatter()))
    scored = assess({"packed": True, "entropy": 7.976}, net, ran=True)

    assert scored["score"] == 15
    assert scored["verdict"] == "unknown"
    assert scored["mitre"] == ["T1027"]        # packing only, no network claim
    assert "T1071.004" not in scored["mitre"]
    assert "T1571" not in scored["mitre"]


def test_the_7z_runs_no_longer_read_suspicious(tmp_path):
    """Archives could not even set packed, so their 40 was pure noise."""
    net, _ = parse(_write(tmp_path / "arc.pcap", _chatter()))
    scored = assess({"packed": False}, net, ran=True)

    assert scored["score"] == 0
    assert scored["verdict"] == "unknown"
    assert scored["mitre"] == []


# -- real behaviour still lands ------------------------------------------------


def test_real_callouts_survive_the_filter(tmp_path):
    packets = _chatter() + [
        scapy_all.Ether()
        / scapy_all.IP(src="169.254.11.5", dst="203.0.113.10")
        / scapy_all.TCP(sport=40001, dport=4444, flags="S"),
        scapy_all.Ether()
        / scapy_all.IP(src="169.254.11.5", dst="203.0.113.53")
        / scapy_all.UDP(sport=50001, dport=53)
        / scapy_all.DNS(qd=scapy_all.DNSQR(qname="c2.example.com")),
    ]
    net, events = parse(_write(tmp_path / "mixed.pcap", packets))

    assert net.syn_attempts == 1
    assert net.ports == [4444]
    assert "203.0.113.10" in net.ips
    assert net.dns_queries == 1
    assert net.domains == ["c2.example.com"]
    assert net.baseline == len(_chatter())

    scored = assess({"packed": True}, net, ran=True)
    assert "T1571" in scored["mitre"]        # 4444 really is a non-standard port
    assert "T1071.004" in scored["mitre"]
    assert scored["verdict"] in ("suspicious", "malicious")


def test_a_sample_talking_to_a_multicast_group_is_still_suppressed(tmp_path):
    """Deliberate design choice, worth stating: a sample that only ever
    multicasts is indistinguishable from the guest doing the same, so it is
    suppressed rather than guessed at. The packet count keeps it visible."""
    packets = [
        scapy_all.Ether()
        / scapy_all.IP(src="169.254.11.5", dst="239.1.2.3")
        / scapy_all.UDP(sport=5000, dport=31337)
        / scapy_all.Raw(load=b"beacon"),
    ]
    net, _ = parse(_write(tmp_path / "mc.pcap", packets))
    assert net.packets == 0 and net.baseline == 1
