"""Outbound TLS trust (palestrix/tls.py).

The regression these guard: Proxmox signs its API certificate with a cluster
root CA that carries no keyUsage extension, and Python 3.13+ enables
ssl.VERIFY_X509_STRICT by default, which rejects such a CA with
"CA cert does not include key usage extension". The fixtures below build a
CA of exactly that shape and drive a real handshake against it, so the
assertions are about verification behaviour and not about a flag's value.
"""

import datetime
import socket
import ssl
import threading

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from palestrix.tls import TrustConfigError, client_verify, trust_context


def _name(cn):
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])


@pytest.fixture(scope="module")
def pve_shaped_pki(tmp_path_factory):
    """A CA with basicConstraints but *no* keyUsage -- what Proxmox generates
    -- plus a leaf for localhost. Returns (ca_pem_path, cert_path, key_path)."""
    now = datetime.datetime.now(datetime.timezone.utc)
    day = datetime.timedelta(days=1)

    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(_name("PVE Cluster Manager CA"))
        .issuer_name(_name("PVE Cluster Manager CA"))
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - day)
        .not_valid_after(now + 365 * day)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()),
            critical=False,
        )
        # deliberately no KeyUsage -- this is the whole point of the fixture,
        # and the only strict-mode violation the chain is left with
        .sign(ca_key, hashes.SHA256())
    )

    leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    leaf_cert = (
        x509.CertificateBuilder()
        .subject_name(_name("localhost"))
        .issuer_name(ca_cert.subject)
        .public_key(leaf_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - day)
        .not_valid_after(now + 365 * day)
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False
        )
        .add_extension(
            x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(leaf_key.public_key()),
            critical=False,
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )

    root = tmp_path_factory.mktemp("pki")
    ca_pem = root / "pve-root-ca.pem"
    cert_pem = root / "pve-ssl.pem"
    key_pem = root / "pve-ssl.key"
    enc = serialization.Encoding.PEM
    ca_pem.write_bytes(ca_cert.public_bytes(enc))
    cert_pem.write_bytes(leaf_cert.public_bytes(enc))
    key_pem.write_bytes(
        leaf_key.private_bytes(
            enc,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    return str(ca_pem), str(cert_pem), str(key_pem)


def _handshake(client_ctx, cert_path, key_path):
    """One TLS handshake against a throwaway localhost server. Raises whatever
    the client side raises."""
    server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_ctx.load_cert_chain(cert_path, key_path)

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]

    def serve():
        try:
            raw, _ = listener.accept()
            with raw, server_ctx.wrap_socket(raw, server_side=True):
                pass
        except OSError:
            pass  # client rejected us mid-handshake; that is the case under test
        finally:
            listener.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=10) as sock:
            with client_ctx.wrap_socket(sock, server_hostname="localhost") as tls:
                return tls.version()
    finally:
        thread.join(timeout=10)


def test_stock_context_rejects_a_proxmox_shaped_ca(pve_shaped_pki):
    """Sanity check on the premise: without the fix, this is the live error."""
    ca_pem, cert_pem, key_pem = pve_shaped_pki
    stock = ssl.create_default_context(cafile=ca_pem)
    if not stock.verify_flags & ssl.VERIFY_X509_STRICT:
        pytest.skip("runtime predates strict-by-default; nothing to regress")
    with pytest.raises(ssl.SSLCertVerificationError) as exc:
        _handshake(stock, cert_pem, key_pem)
    assert "key usage" in str(exc.value)


def test_trust_context_accepts_a_proxmox_shaped_ca(pve_shaped_pki):
    ca_pem, cert_pem, key_pem = pve_shaped_pki
    assert _handshake(trust_context(ca_pem), cert_pem, key_pem).startswith("TLS")


def test_trust_context_still_verifies_the_chain(pve_shaped_pki, tmp_path):
    """Relaxing strict mode must not become 'trust anything': a leaf signed by
    some other CA is still rejected."""
    _, cert_pem, key_pem = pve_shaped_pki
    stranger = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.datetime.now(datetime.timezone.utc)
    other_ca = (
        x509.CertificateBuilder()
        .subject_name(_name("Unrelated CA"))
        .issuer_name(_name("Unrelated CA"))
        .public_key(stranger.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(stranger.public_key()),
            critical=False,
        )
        .sign(stranger, hashes.SHA256())
    )
    other_pem = tmp_path / "other-ca.pem"
    other_pem.write_bytes(other_ca.public_bytes(serialization.Encoding.PEM))

    with pytest.raises(ssl.SSLCertVerificationError):
        _handshake(trust_context(str(other_pem)), cert_pem, key_pem)


def test_trust_context_still_verifies_the_hostname(pve_shaped_pki):
    """The live deployment points at an IP the PVE cert does not carry; that
    must keep failing rather than ride along with the strict-mode relaxation."""
    ca_pem, cert_pem, key_pem = pve_shaped_pki
    ctx = trust_context(ca_pem)
    assert ctx.check_hostname is True
    assert ctx.verify_mode is ssl.CERT_REQUIRED


def test_client_verify_modes(pve_shaped_pki):
    ca_pem, _, _ = pve_shaped_pki
    assert client_verify(False, ca_pem) is False  # guard-refused, but honoured
    assert client_verify(False, "") is False
    assert client_verify(True, "") is True  # system trust store, stock defaults
    assert isinstance(client_verify(True, ca_pem), ssl.SSLContext)


def test_trust_context_is_cached(pve_shaped_pki):
    ca_pem, _, _ = pve_shaped_pki
    assert trust_context(ca_pem) is trust_context(ca_pem)


def test_unusable_bundle_is_reported(tmp_path):
    with pytest.raises(TrustConfigError):
        trust_context(str(tmp_path / "nope.pem"))
    junk = tmp_path / "junk.pem"
    junk.write_text("not a certificate")
    with pytest.raises(TrustConfigError):
        trust_context(str(junk))


def test_boot_guard_flags_an_unusable_bundle(tmp_path):
    from palestrix.config import Settings
    from palestrix.hardening import production_readiness

    settings = Settings(proxmox_host="https://pve:8006", proxmox_ca_bundle=str(tmp_path / "missing.pem"))
    findings = production_readiness(settings)
    assert any("PROXMOX_CA_BUNDLE is unusable" in f for f in findings)
