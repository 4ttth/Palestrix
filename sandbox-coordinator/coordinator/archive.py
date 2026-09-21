"""Archive unwrapping.

Samples are shared as password-protected archives because that is how the
industry moves malware without every mail gateway and scanner eating it in
transit. "infected" is the near-universal convention. An archive that is never
opened is a sample that never detonates: the container is what gets copied to
the guest, Windows has no handler for it, and the run looks inert for a reason
that has nothing to do with the sample.

Unwrapping also fixes a static false positive. Compressed containers sit near
8.0 bits/byte by construction, so *every* archive trips the packed heuristic
and every verdict inherits a meaningless T1027. Scoring the inner file instead
describes the sample rather than the envelope.

Extraction is hostile-input handling, so the limits below are the point, not
boilerplate: an archive is attacker-controlled and may be a zip bomb, a path
traversal, or a million empty files.
"""

from __future__ import annotations

import io
import os
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass, field

# Tried in order. The empty password covers unencrypted archives; the rest are
# the conventions seen on sample exchanges and in coursework handouts.
PASSWORDS = ("", "infected", "malware", "virus", "p@ssw0rd")

MAX_ENTRIES = 256
MAX_TOTAL_BYTES = 256 * 1024 * 1024
MAX_ENTRY_BYTES = 128 * 1024 * 1024

# Extensions that are worth detonating, most interesting first. Used to pick
# the payload when an archive holds more than one file.
RUNNABLE = (
    ".exe", ".dll", ".scr", ".com", ".msi", ".bat", ".cmd",
    ".ps1", ".vbs", ".js", ".jse", ".wsf", ".hta", ".lnk", ".jar",
)

MAGIC = (
    (b"7z\xbc\xaf\x27\x1c", "7z"),
    (b"PK\x03\x04", "zip"),
    (b"PK\x05\x06", "zip"),
    (b"Rar!\x1a\x07", "rar"),
    (b"\x1f\x8b", "gzip"),
    (b"BZh", "bzip2"),
    (b"\xfd7zXZ\x00", "xz"),
)


@dataclass
class Entry:
    name: str
    data: bytes


@dataclass
class Extracted:
    kind: str
    entries: list[Entry] = field(default_factory=list)
    password: str | None = None      # which candidate opened it
    encrypted: bool = False
    error: str | None = None
    truncated: bool = False

    @property
    def ok(self) -> bool:
        return bool(self.entries)


def sniff(data: bytes) -> str | None:
    """The archive kind, or None if this is not a container we unwrap."""
    for sig, kind in MAGIC:
        if data.startswith(sig):
            return kind
    # tar has no leading magic; its "ustar" marker sits at offset 257.
    if len(data) > 262 and data[257:262] in (b"ustar",):
        return "tar"
    return None


def _safe_name(name: str) -> str | None:
    """Reject anything that tries to escape the extraction directory.

    Refused rather than sanitised: a member named ..\\..\\system32\\x is a
    hostile archive, and quietly renaming it would hide that from the analyst.
    """
    name = name.replace("\\", "/")
    if not name or name.endswith("/"):
        return None
    if name.startswith("/") or ".." in name.split("/"):
        return None
    if len(name) > 2 and name[1] == ":":      # C:\...
        return None
    return os.path.basename(name) or None


def _accumulate(out: Extracted, name: str, data: bytes, total: list[int]) -> bool:
    """Append one member, honouring the caps. False means stop reading."""
    safe = _safe_name(name)
    if safe is None:
        return True                            # skip, keep going
    if len(data) > MAX_ENTRY_BYTES:
        out.truncated = True
        return True
    if total[0] + len(data) > MAX_TOTAL_BYTES or len(out.entries) >= MAX_ENTRIES:
        out.truncated = True
        return False
    total[0] += len(data)
    out.entries.append(Entry(safe, data))
    return True


def _plan(sizes: list[tuple[object, str, int]], out: Extracted) -> list[object]:
    """Decide which members to materialise, from declared sizes alone.

    A bomb is refused from the header rather than survived after the fact:
    decompressing 10 GB to discover it was 10 GB has already cost the host
    the 10 GB.
    """
    keep: list[object] = []
    total = 0
    for handle, name, size in sizes:
        if _safe_name(name) is None:
            continue                       # hostile path, refused outright
        if (
            size > MAX_ENTRY_BYTES
            or len(keep) >= MAX_ENTRIES
            or total + size > MAX_TOTAL_BYTES
        ):
            out.truncated = True
            continue
        total += size
        keep.append(handle)
    return keep


def _extract_zip(data: bytes, out: Extracted) -> None:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except Exception as exc:
        out.error = f"not a readable zip: {exc}"
        return

    members = [i for i in zf.infolist() if not i.is_dir()]
    out.encrypted = any(i.flag_bits & 0x1 for i in members)
    planned = _plan([(i, i.filename, i.file_size) for i in members], out)

    for pw in PASSWORDS:
        entries: list[Entry] = []
        try:
            for info in planned:
                with zf.open(info, pwd=pw.encode() if pw else None) as fh:
                    blob = fh.read(MAX_ENTRY_BYTES)
                safe = _safe_name(info.filename)
                if safe is not None:
                    entries.append(Entry(safe, blob))
        except RuntimeError as exc:
            # zipfile raises RuntimeError for a bad password.
            if "password" in str(exc).lower():
                continue
            out.error = str(exc)
            return
        except NotImplementedError as exc:
            # AES-encrypted zips need pyzipper; stdlib only does ZipCrypto.
            out.error = f"unsupported zip encryption ({exc}); pyzipper not installed"
            return
        except Exception as exc:
            out.error = str(exc)
            return
        # Reading through without a password error means this candidate was
        # the right one -- even if every member was filtered by the caps.
        out.entries = entries
        out.password = pw
        return
    out.error = "no candidate password opened this zip"


def _extract_7z(data: bytes, out: Extracted) -> None:
    try:
        import py7zr
    except ImportError:
        out.error = (
            "7-Zip archive needs py7zr on the coordinator "
            "(pip install py7zr); sample left wrapped"
        )
        return

    for pw in PASSWORDS:
        out.entries = []
        try:
            with py7zr.SevenZipFile(
                io.BytesIO(data), mode="r", password=pw or None
            ) as zf:
                out.encrypted = zf.needs_password()
                if out.encrypted and not pw:
                    continue        # the empty candidate cannot open this one

                infos = [i for i in zf.list() if not i.is_directory]
                planned = _plan(
                    [(i.filename, i.filename, i.uncompressed or 0) for i in infos],
                    out,
                )
                if not planned:
                    out.password = pw
                    return

                # py7zr has no in-memory read API, so members land in a
                # throwaway staging directory and are read back from there.
                zf.reset()
                with tempfile.TemporaryDirectory() as stage:
                    zf.extract(path=stage, targets=list(planned))
                    root = os.path.realpath(stage)
                    for dirpath, _dirs, files in os.walk(stage):
                        for fn in sorted(files):
                            full = os.path.realpath(os.path.join(dirpath, fn))
                            # Belt and braces: never read back anything the
                            # archive managed to place outside the staging
                            # directory.
                            if not full.startswith(root + os.sep):
                                continue
                            safe = _safe_name(os.path.relpath(full, root))
                            if safe is None:
                                continue
                            with open(full, "rb") as fh:
                                out.entries.append(Entry(safe, fh.read()))
            out.password = pw
            return
        except Exception as exc:
            out.entries = []
            name = type(exc).__name__
            blob = (name + " " + str(exc)).lower()
            # A wrong password surfaces as a decompression failure, not as
            # anything that says "password".
            if any(k in blob for k in ("password", "lzma", "crc", "corrupt", "checksum")):
                continue
            out.error = str(exc)
            return
    out.error = "no candidate password opened this 7z"


def _extract_tarlike(data: bytes, out: Extracted) -> None:
    try:
        tf = tarfile.open(fileobj=io.BytesIO(data), mode="r:*")
    except Exception as exc:
        out.error = f"not a readable tar/gzip stream: {exc}"
        return
    total = [0]
    try:
        for member in tf:
            if not member.isfile():
                continue
            # Refuse from the header where we can: a tar member declares its
            # size, so a bomb does not have to be decompressed to be caught.
            if member.size > MAX_ENTRY_BYTES:
                out.truncated = True
                continue
            fh = tf.extractfile(member)
            if fh is None:
                continue
            # Bounded read even so. The declared size is attacker-controlled
            # and gzip/xz members do not have to agree with it, so an
            # unbounded read() here decompresses whatever the stream feeds
            # it straight into the coordinator's memory -- before the cap
            # below ever gets a chance to look at the length.
            blob = fh.read(MAX_ENTRY_BYTES + 1)
            if len(blob) > MAX_ENTRY_BYTES:
                out.truncated = True
                continue
            if not _accumulate(out, member.name, blob, total):
                break
    except Exception as exc:
        out.error = str(exc)
    out.password = ""


def extract(data: bytes) -> Extracted | None:
    """Unwrap ``data`` if it is a supported container, else None."""
    kind = sniff(data)
    if kind is None:
        return None
    out = Extracted(kind=kind)

    if kind == "zip":
        _extract_zip(data, out)
    elif kind == "7z":
        _extract_7z(data, out)
    elif kind in ("tar", "gzip", "bzip2", "xz"):
        _extract_tarlike(data, out)
    elif kind == "rar":
        out.error = "RAR needs the unrar binary; sample left wrapped"
    return out


def pick_payload(entries: list[Entry]) -> Entry | None:
    """Choose what to actually detonate.

    A runnable extension wins over a document, and among equals the largest
    file wins -- readme.txt and the icon should not beat the dropper.
    """
    if not entries:
        return None

    def rank(e: Entry) -> tuple[int, int]:
        lower = e.name.lower()
        for i, ext in enumerate(RUNNABLE):
            if lower.endswith(ext):
                return (len(RUNNABLE) - i, len(e.data))
        return (0, len(e.data))

    return max(entries, key=rank)


def events(out: Extracted, chosen: Entry | None) -> list[dict]:
    """Analyst-facing timeline entries for the unwrap step."""
    ev: list[dict] = []
    if out.error:
        ev.append({
            "category": "static",
            "level": "warn",
            "msg": f"{out.kind} archive not opened: {out.error}",
            "data": {"kind": out.kind},
        })
        return ev

    how = f" with password '{out.password}'" if out.password else ""
    ev.append({
        "category": "static",
        "level": "info",
        "msg": f"{out.kind} archive opened{how}: {len(out.entries)} file(s)",
        "data": {
            "kind": out.kind,
            "entries": [e.name for e in out.entries[:50]],
            "encrypted": out.encrypted,
        },
    })
    if out.truncated:
        ev.append({
            "category": "static",
            "level": "warn",
            "msg": "archive truncated at the extraction limit "
                   f"({MAX_ENTRIES} files / {MAX_TOTAL_BYTES // (1024 * 1024)} MB)",
            "data": {},
        })
    if chosen is not None:
        ev.append({
            "category": "static",
            "level": "info",
            "msg": f"detonating '{chosen.name}' from the archive "
                   f"({len(chosen.data)} bytes)",
            "data": {"name": chosen.name, "size": len(chosen.data)},
        })
    return ev
