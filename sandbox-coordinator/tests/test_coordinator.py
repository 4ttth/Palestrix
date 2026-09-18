"""Logic tests for the coordinator. No VM, no root, no samples required."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coordinator.payload import RUN_BAT, safe_name  # noqa: E402
from coordinator.pcapparse import NetFacts, parse  # noqa: E402
from coordinator.staticcheck import analyse, static_events  # noqa: E402
from coordinator.verdict import assess  # noqa: E402

EICAR = (
    rb"X5O!P%@AP[4\PZX54(P^)7CC)7}$"
    + b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE!"
    + b"$H+H*"
)


def test_eicar_is_detected_and_scored_max():
    static, _ = analyse("eicar.com", EICAR)
    assert static["eicar"] is True
    out = assess(static, NetFacts(), ran=True)
    assert out["verdict"] == "malicious"
    assert out["score"] == 100
    assert out["family"] == "EICAR-Test-File"


def test_pe_magic_and_iocs_from_strings():
    blob = b"MZ" + b"\x00" * 64 + b"http://evil.example/c2.php beacon 10.20.30.40 "
    static, iocs = analyse("dropper.exe", blob)
    assert static["type"] == "pe"
    assert "http://evil.example/c2.php" in iocs["urls"]
    assert "10.20.30.40" in iocs["ips"]


def test_high_entropy_flags_packed():
    static, _ = analyse("packed.exe", b"MZ" + os.urandom(200_000))
    assert static["packed"] is True
    assert any(e["level"] == "warn" for e in static_events(static))


def test_network_behaviour_drives_verdict_and_mitre():
    net = NetFacts(
        domains=["c2.example"],
        ips=["203.0.113.5"],
        urls=["http://c2.example/gate"],
        ports=[4444],
        dns_queries=1,
        http_requests=1,
        syn_attempts=2,
        packets=40,
    )
    out = assess({"packed": False, "eicar": False}, net, ran=True)
    assert out["verdict"] == "malicious"
    assert "T1071.001" in out["mitre"]  # web protocols
    assert "T1071.004" in out["mitre"]  # DNS
    assert "T1571" in out["mitre"]      # non-standard port 4444


def test_silence_is_unknown_not_clean():
    """An air-gapped run that saw nothing must never claim the sample is clean."""
    out = assess({"packed": False, "eicar": False}, NetFacts(packets=0), ran=True)
    assert out["verdict"] == "unknown"


def test_missing_pcap_degrades_gracefully():
    facts, events = parse("/nonexistent/capture.pcap")
    assert isinstance(facts, NetFacts)
    assert isinstance(events, list)


def test_filename_cannot_escape_or_inject():
    # basename() strips the directory outright, so traversal cannot survive.
    assert safe_name("../../../etc/shadow") == "shadow"
    # Backslashes are not separators on POSIX, so the charset filter catches them.
    assert "\\" not in safe_name(r"..\..\windows\system32\evil.exe")
    assert ";" not in safe_name("a;rm -rf /.exe")
    assert safe_name("") == "sample.bin"
    assert RUN_BAT.format(name=safe_name("x.exe")).count("\\") >= 2
