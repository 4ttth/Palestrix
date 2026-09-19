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


def test_wall_clock_caps_the_detonation_window():
    """The ceiling counts ISO build and clone time, not just the sleep."""
    from types import SimpleNamespace

    from coordinator.main import detonation_sleep

    s = SimpleNamespace(
        boot_grace_seconds=45, detonation_seconds=180, wall_clock_seconds=300
    )
    # A fast clone: the analyst's full window fits under the ceiling.
    assert detonation_sleep(s, elapsed=10.0) == 225.0
    # A slow clone eats into it rather than extending the run past 300s.
    assert detonation_sleep(s, elapsed=120.0) == 180.0
    # Already over budget: hold the VM open for nothing at all.
    assert detonation_sleep(s, elapsed=400.0) == 0.0


def test_wall_clock_below_the_window_wins():
    """A deployment that sets a tighter ceiling than the requested window
    gets the ceiling, not the window."""
    from types import SimpleNamespace

    from coordinator.main import detonation_sleep

    s = SimpleNamespace(
        boot_grace_seconds=45, detonation_seconds=180, wall_clock_seconds=60
    )
    assert detonation_sleep(s, elapsed=0.0) == 60.0


def _client_hello(server_name: str) -> bytes:
    """A minimal TLS ClientHello carrying one SNI extension."""
    import struct

    name = server_name.encode("ascii")
    sni = struct.pack(">H", len(name) + 3) + b"\x00" + struct.pack(">H", len(name)) + name
    ext = struct.pack(">HH", 0x0000, len(sni)) + sni

    body = b"\x03\x03" + b"\xab" * 32          # version + random
    body += b"\x00"                             # session id length
    body += struct.pack(">H", 2) + b"\x13\x01"  # cipher suites
    body += b"\x01\x00"                         # compression methods
    body += struct.pack(">H", len(ext)) + ext

    handshake = b"\x01" + len(body).to_bytes(3, "big") + body
    return b"\x16\x03\x01" + struct.pack(">H", len(handshake)) + handshake


def test_sni_is_extracted_from_a_client_hello():
    """Regression: the extractor decoded the host with .decode("idna",
    "ignore"), and "idna" is the one codec that raises on a lenient error
    handler rather than being lenient. Every ClientHello therefore threw
    UnicodeError into the function's own except and returned None, so the
    TLS branch and T1573 were unreachable in production."""
    from coordinator.pcapparse import _sni_from_client_hello

    assert _sni_from_client_hello(_client_hello("c2.example")) == "c2.example"
    assert _sni_from_client_hello(_client_hello("a.b.c.example")) == "a.b.c.example"


def test_sni_extractor_rejects_non_tls_payloads():
    from coordinator.pcapparse import _sni_from_client_hello

    assert _sni_from_client_hello(b"GET / HTTP/1.1\r\nHost: x\r\n\r\n") is None
    assert _sni_from_client_hello(b"\x16\x03\x01") is None
    assert _sni_from_client_hello(b"") is None


def test_tls_sni_drives_the_verdict():
    """With the extractor working, a ClientHello must reach T1573."""
    out = assess({}, NetFacts(sni=["c2.example"], packets=1), ran=True)
    assert "T1573" in out["mitre"]
    assert out["score"] >= 20
