"""Turn the capture into behaviour events and IOCs.

Nothing on the sandbox bridge answers, so flows never complete. That is fine
and in fact useful: an unanswered SYN still names the C2 the sample wanted,
and a DNS question still names the domain. Everything here is derived from
what the sample *attempted*.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field


@dataclass
class NetFacts:
    domains: list[str] = field(default_factory=list)
    ips: list[str] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)
    sni: list[str] = field(default_factory=list)
    ports: list[int] = field(default_factory=list)
    dns_queries: int = 0
    syn_attempts: int = 0
    http_requests: int = 0
    packets: int = 0      # packets that could carry a finding
    baseline: int = 0     # suppressed guest chatter


# Ports the guest shouts into the void on its own initiative. These cover the
# unicast cases; the multicast ones are already caught by destination.
BASELINE_PORTS = frozenset({
    5353,        # mDNS
    5355,        # LLMNR
    137, 138,    # NetBIOS name / datagram
    67, 68,      # DHCP
    546, 547,    # DHCPv6
    1900,        # SSDP
    3702,        # WS-Discovery
    5350, 5351,  # NAT-PMP
})

# Suffixes that only appear in link-local name resolution. A sample resolving
# one of these has not named a C2 -- the guest has named itself.
BASELINE_SUFFIXES = (".local", ".arpa", ".localdomain")


def is_baseline_dst(ip: str) -> bool:
    """True when the destination is nobody in particular.

    Multicast, limited broadcast and link-local (APIPA) destinations are
    discovery by construction: no host on the other end was *chosen*.
    """
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return bool(
        addr.is_multicast
        or addr.is_link_local
        or addr.is_loopback
        or addr.is_unspecified
        or (addr.version == 4 and int(addr) == 0xFFFFFFFF)
    )


def is_baseline_name(qname: str) -> bool:
    lowered = qname.lower().rstrip(".")
    if not lowered or "." not in lowered:
        return True          # single label: NetBIOS/LLMNR, never a C2 domain
    return lowered.endswith(BASELINE_SUFFIXES)


HTTP_METHODS = (b"GET ", b"POST ", b"HEAD ", b"PUT ", b"DELETE ", b"OPTIONS ", b"PATCH ")


def _sni_from_client_hello(payload: bytes) -> str | None:
    """Minimal TLS ClientHello SNI extraction (no crypto, no dependencies)."""
    try:
        if len(payload) < 45 or payload[0] != 0x16:
            return None
        # record(5) + handshake header(4) + version(2) + random(32)
        i = 5 + 4 + 2 + 32
        i += 1 + payload[i]                      # session id
        i += 2 + int.from_bytes(payload[i:i + 2], "big")   # cipher suites
        i += 1 + payload[i]                      # compression methods
        i += 2                                   # extensions length
        end = len(payload)
        while i + 4 <= end:
            etype = int.from_bytes(payload[i:i + 2], "big")
            elen = int.from_bytes(payload[i + 2:i + 4], "big")
            body = payload[i + 4:i + 4 + elen]
            if etype == 0x0000 and len(body) >= 5:
                name_len = int.from_bytes(body[3:5], "big")
                raw = body[5:5 + name_len]
                try:
                    # Strict on purpose: "idna" is the one codec that raises
                    # on a lenient error handler instead of being lenient, so
                    # decode(..., "ignore") threw UnicodeError on every
                    # ClientHello and this function silently returned None --
                    # the SNI branch and T1573 never fired at all.
                    return raw.decode("idna") or None
                except Exception:
                    # Malformed or non-punycode label: keep the indicator
                    # rather than losing it entirely.
                    return raw.decode("ascii", "ignore") or None
            i += 4 + elen
    except Exception:
        return None
    return None


def parse(pcap_path: str) -> tuple[NetFacts, list[dict]]:
    facts = NetFacts()
    events: list[dict] = []

    try:
        from scapy.all import DNS, DNSQR, IP, TCP, UDP, Raw, PcapReader
    except Exception:
        return facts, [
            {
                "category": "system",
                "level": "warn",
                "msg": "network capture not parsed (scapy unavailable)",
                "data": {},
            }
        ]

    def note(level: str, msg: str, **data):
        events.append(
            {"category": "network", "level": level, "msg": msg, "data": data}
        )

    seen_dns: set[str] = set()
    seen_conn: set[tuple[str, int]] = set()
    seen_http: set[str] = set()
    seen_sni: set[str] = set()

    try:
        reader = PcapReader(pcap_path)
    except Exception:
        return facts, events

    with reader:
        for pkt in reader:
            # Suppress the guest's own discovery chatter before anything can
            # score on it. Without this every capture yields a "DNS lookup"
            # for the VM's hostname and a "non-standard port" for mDNS --
            # 40 points that describe Windows, not the sample.
            dst = pkt[IP].dst if pkt.haslayer(IP) else None
            dport = None
            if pkt.haslayer(UDP):
                dport = int(pkt[UDP].dport)
            elif pkt.haslayer(TCP):
                dport = int(pkt[TCP].dport)
            if (dst is not None and is_baseline_dst(dst)) or (
                dport is not None and dport in BASELINE_PORTS
            ):
                facts.baseline += 1
                continue

            facts.packets += 1

            if pkt.haslayer(DNS) and pkt.haslayer(DNSQR) and pkt[DNS].qr == 0:
                try:
                    qname = pkt[DNSQR].qname.decode("utf-8", "ignore").rstrip(".")
                except Exception:
                    qname = ""
                if qname and is_baseline_name(qname):
                    facts.baseline += 1
                    facts.packets -= 1
                    continue
                if qname and qname not in seen_dns:
                    seen_dns.add(qname)
                    facts.dns_queries += 1
                    facts.domains.append(qname)
                    note("alert", f"DNS lookup for {qname}", domain=qname)

            if pkt.haslayer(TCP) and pkt.haslayer(IP):
                tcp, ip = pkt[TCP], pkt[IP]
                # SYN without ACK == an outbound connection attempt
                if tcp.flags & 0x02 and not tcp.flags & 0x10:
                    key = (ip.dst, int(tcp.dport))
                    if key not in seen_conn:
                        seen_conn.add(key)
                        facts.syn_attempts += 1
                        facts.ips.append(ip.dst)
                        facts.ports.append(int(tcp.dport))
                        note(
                            "alert",
                            f"connection attempt to {ip.dst}:{tcp.dport}",
                            ip=ip.dst,
                            port=int(tcp.dport),
                            transport="tcp",
                        )

                if pkt.haslayer(Raw):
                    payload = bytes(pkt[Raw].load)
                    if payload.startswith(HTTP_METHODS):
                        try:
                            head = payload.split(b"\r\n\r\n", 1)[0].decode(
                                "utf-8", "ignore"
                            )
                            lines = head.split("\r\n")
                            method, path = lines[0].split(" ")[:2]
                            host = ""
                            for ln in lines[1:]:
                                if ln.lower().startswith("host:"):
                                    host = ln.split(":", 1)[1].strip()
                                    break
                            url = f"http://{host}{path}" if host else path
                            if url not in seen_http:
                                seen_http.add(url)
                                facts.http_requests += 1
                                facts.urls.append(url)
                                note(
                                    "alert",
                                    f"HTTP {method} {url}",
                                    method=method,
                                    url=url,
                                    host=host,
                                )
                        except Exception:
                            pass
                    else:
                        sni = _sni_from_client_hello(payload)
                        if sni and sni not in seen_sni:
                            seen_sni.add(sni)
                            facts.sni.append(sni)
                            facts.domains.append(sni)
                            note("alert", f"TLS ClientHello for {sni}", sni=sni)

            elif pkt.haslayer(UDP) and pkt.haslayer(IP):
                udp, ip = pkt[UDP], pkt[IP]
                if int(udp.dport) not in (53, 67, 68, 137, 138, 5355, 1900):
                    key = (ip.dst, int(udp.dport))
                    if key not in seen_conn:
                        seen_conn.add(key)
                        facts.ips.append(ip.dst)
                        facts.ports.append(int(udp.dport))
                        note(
                            "warn",
                            f"UDP traffic to {ip.dst}:{udp.dport}",
                            ip=ip.dst,
                            port=int(udp.dport),
                            transport="udp",
                        )

    if facts.baseline:
        events.append(
            {
                "category": "network",
                "level": "info",
                "msg": f"suppressed {facts.baseline} baseline packet(s): "
                       "multicast/link-local discovery from the guest itself",
                "data": {"baseline": facts.baseline},
            }
        )
    if facts.packets == 0:
        events.append(
            {
                "category": "network",
                "level": "info",
                "msg": "no network traffic attributable to the sample"
                       if facts.baseline
                       else "no network traffic observed during detonation",
                "data": {},
            }
        )
    return facts, events
