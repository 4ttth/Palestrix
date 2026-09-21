"""Archive unwrapping.

Samples arrive wrapped, usually under the password "infected". An archive
that is never opened is a sample that never detonates -- the container goes
to the guest, Windows has no handler for it, and the run looks inert for a
reason that has nothing to do with the sample.
"""

import io
import os
import sys
import tarfile
import zipfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coordinator import archive  # noqa: E402

EICAR = (
    rb"X5O!P%@AP[4\PZX54(P^)7CC)7}$"
    + b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE!"
    + b"$H+H*"
)


def _zip(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


def _targz(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


# -- sniffing ------------------------------------------------------------------


def test_sniff_recognises_the_containers_we_unwrap():
    assert archive.sniff(_zip({"a.txt": b"x"})) == "zip"
    assert archive.sniff(_targz({"a.txt": b"x"})) == "gzip"
    assert archive.sniff(b"7z\xbc\xaf\x27\x1c" + b"\x00" * 32) == "7z"
    assert archive.sniff(b"Rar!\x1a\x07\x00") == "rar"


def test_sniff_passes_through_a_plain_executable():
    assert archive.sniff(b"MZ" + b"\x00" * 64) is None
    assert archive.extract(b"MZ" + b"\x00" * 64) is None


# -- zip -----------------------------------------------------------------------


def test_plain_zip_is_opened():
    out = archive.extract(_zip({"dropper.exe": b"MZ payload", "notes.txt": b"hi"}))
    assert out.ok and out.kind == "zip"
    assert {e.name for e in out.entries} == {"dropper.exe", "notes.txt"}
    assert out.error is None


def test_eicar_survives_the_round_trip():
    """The unwrapped bytes must be the sample, not a mangled copy."""
    out = archive.extract(_zip({"eicar.com": EICAR}))
    assert out.entries[0].data == EICAR


# -- 7z, the reported bug ------------------------------------------------------


py7zr = pytest.importorskip("py7zr", reason="7z support needs py7zr")


def _sevenzip(members: dict[str, bytes], password: str | None = None) -> bytes:
    buf = io.BytesIO()
    with py7zr.SevenZipFile(buf, mode="w", password=password) as zf:
        for name, data in members.items():
            zf.writef(io.BytesIO(data), name)
    return buf.getvalue()


def test_plain_7z_is_opened():
    out = archive.extract(_sevenzip({"dropper.exe": b"MZ payload"}))
    assert out.ok, out.error
    assert out.entries[0].name == "dropper.exe"
    assert out.entries[0].data == b"MZ payload"


def test_7z_under_the_infected_password_is_opened():
    """The convention the UI advertises. This is the case that was broken."""
    blob = _sevenzip({"dropper.exe": b"MZ real payload"}, password="infected")
    out = archive.extract(blob)
    assert out.ok, out.error
    assert out.password == "infected"
    assert out.entries[0].data == b"MZ real payload"


def test_7z_with_an_unknown_password_reports_rather_than_pretends():
    blob = _sevenzip({"x.exe": b"MZ"}, password="not-a-candidate-9f2b")
    out = archive.extract(blob)
    assert not out.ok
    assert out.error and "password" in out.error.lower()


# -- tar/gzip ------------------------------------------------------------------


def test_targz_is_opened():
    out = archive.extract(_targz({"payload.sh": b"#!/bin/sh\necho hi\n"}))
    assert out.ok and out.entries[0].name == "payload.sh"


# -- hostile input -------------------------------------------------------------


def test_path_traversal_members_are_refused():
    out = archive.extract(_zip({"../../evil.exe": b"MZ", "ok.exe": b"MZ2"}))
    names = {e.name for e in out.entries}
    assert "ok.exe" in names
    assert not any(".." in n or "/" in n or "\\" in n for n in names)


def test_absolute_and_drive_qualified_members_are_refused():
    assert archive._safe_name("/etc/passwd") is None
    assert archive._safe_name(r"C:\windows\system32\evil.exe") is None
    assert archive._safe_name("../../x") is None
    assert archive._safe_name("plain.exe") == "plain.exe"


def test_entry_count_is_capped():
    many = {f"f{i}.txt": b"x" for i in range(archive.MAX_ENTRIES + 40)}
    out = archive.extract(_zip(many))
    assert len(out.entries) <= archive.MAX_ENTRIES
    assert out.truncated


def test_a_decompression_bomb_is_refused_from_the_header(monkeypatch):
    """The cap is applied to declared sizes, so the bomb is never inflated.

    The caps are lowered here rather than building a real 256 MB bomb: the
    property under test is that the decision comes from the central
    directory, and materialising a quarter-gigabyte of zeroes to prove it
    would be the very thing the code exists to avoid.
    """
    monkeypatch.setattr(archive, "MAX_TOTAL_BYTES", 4096)
    monkeypatch.setattr(archive, "MAX_ENTRY_BYTES", 4096)
    bomb = _zip({"bomb.bin": b"\x00" * 100_000, "small.exe": b"MZ"})
    out = archive.extract(bomb)
    assert out.truncated
    assert {e.name for e in out.entries} == {"small.exe"}
    assert sum(len(e.data) for e in out.entries) <= 4096


# -- payload selection ---------------------------------------------------------


def test_runnable_beats_a_larger_document():
    entries = [
        archive.Entry("readme.txt", b"x" * 10_000),
        archive.Entry("dropper.exe", b"MZ"),
    ]
    assert archive.pick_payload(entries).name == "dropper.exe"


def test_largest_wins_among_equally_runnable_members():
    entries = [
        archive.Entry("small.exe", b"MZ"),
        archive.Entry("big.exe", b"MZ" + b"x" * 5000),
    ]
    assert archive.pick_payload(entries).name == "big.exe"


def test_no_entries_picks_nothing():
    assert archive.pick_payload([]) is None


def test_events_name_the_password_and_the_chosen_payload():
    out = archive.extract(_zip({"dropper.exe": b"MZ", "r.txt": b"x"}))
    chosen = archive.pick_payload(out.entries)
    msgs = " | ".join(e["msg"] for e in archive.events(out, chosen))
    assert "zip archive opened" in msgs
    assert "dropper.exe" in msgs


def test_events_surface_an_unopened_archive_as_a_warning():
    out = archive.Extracted(kind="rar", error="RAR needs the unrar binary")
    ev = archive.events(out, None)
    assert ev[0]["level"] == "warn"
    assert "rar" in ev[0]["msg"]


def test_tar_member_read_is_bounded():
    """A tar member is read under a ceiling, not in full and measured after.

    The cap was applied to the result of an unbounded ``read()``, so a
    compressed member that expands to gigabytes had already been
    materialised in the coordinator's memory by the time anything checked
    its length — on the host whose job is containing live malware.
    """
    import io
    import tarfile

    from coordinator.archive import MAX_ENTRY_BYTES, extract

    buf = io.BytesIO()
    # One highly compressible member well past the per-entry ceiling, plus a
    # small one that must still come through.
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        big = b"\0" * (MAX_ENTRY_BYTES + 4096)
        info = tarfile.TarInfo("bomb.bin")
        info.size = len(big)
        tf.addfile(info, io.BytesIO(big))

        small = b"MZ payload"
        info = tarfile.TarInfo("dropper.exe")
        info.size = len(small)
        tf.addfile(info, io.BytesIO(small))

    out = extract(buf.getvalue())
    assert out is not None
    names = [e.name for e in out.entries]
    assert "bomb.bin" not in names
    assert "dropper.exe" in names
    assert out.truncated
