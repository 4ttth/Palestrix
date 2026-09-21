"""The shipped lab catalog, and the rubric that gates a module on it."""

import hashlib

from sqlalchemy import delete, select

from palestrix.academy_content_loader import load as load_lesson
from palestrix.academy_gate import status_for
from palestrix.db import SessionLocal
from palestrix.labs_catalog import CATALOG, ensure_labs
from palestrix.models import GradingScheme, LabTemplate, Module, Path, RubricItem


def test_every_lab_weights_to_100():
    for spec in CATALOG:
        total = sum(item.weight_percent for item in spec.items)
        assert total == 100, f"{spec.slug} weights total {total}"


def test_rubric_keys_are_unique_within_a_lab():
    for spec in CATALOG:
        keys = [item.key for item in spec.items]
        assert len(keys) == len(set(keys)), f"{spec.slug} has duplicate rubric keys"


def test_expected_hashes_match_the_documented_answers():
    """The rubric hashes must be of `answer + newline`, which is what the
    lesson's `echo 'x' > file` actually writes. A hash of the bare string
    would fail every submission while looking perfectly reasonable here."""
    answers = {
        "source-ip.txt": "203.0.113.45",
        "account.txt": "deploy",
        "method.txt": "publickey",
        "escalated-to.txt": "root",
    }
    spec = next(s for s in CATALOG if s.slug == "log-triage")
    for item in spec.items:
        filename = item.path.rsplit("/", 1)[-1]
        expected = hashlib.sha256((answers[filename] + "\n").encode()).hexdigest()
        assert item.sha256 == expected, f"{item.key} hash does not match {filename}"


def test_the_lesson_binds_to_a_lab_this_catalog_ships():
    """A module naming a lab nobody ships is silently ungated, which is the
    failure mode this pairing exists to prevent."""
    from palestrix.academy_catalog import CATALOG as ACADEMY

    shipped = {spec.slug for spec in CATALOG}
    bound = set()
    for path in ACADEMY:
        for position, module in enumerate(path.modules):
            lesson = load_lesson(path.slug, position, module.title)
            if lesson.lab_slug:
                bound.add(lesson.lab_slug)
    assert bound, "expected at least one lesson to declare a lab"
    assert bound <= shipped, f"lessons name labs with no catalog entry: {bound - shipped}"


def test_applying_is_insert_only_and_idempotent(client):
    db = SessionLocal()
    try:
        first = ensure_labs(db)
        db.commit()
        assert first["error"] is None
        assert "log-triage" in first["created"]

        template = db.scalar(select(LabTemplate).where(LabTemplate.slug == "log-triage"))
        assert template is not None
        assert template.kind == "vm"
        assert template.vm_template == "debian12-min"

        scheme = db.scalar(
            select(GradingScheme).where(GradingScheme.lab_template_id == template.id)
        )
        assert scheme is not None and scheme.status == "published"

        items = db.scalars(
            select(RubricItem)
            .where(RubricItem.scheme_id == scheme.id)
            .order_by(RubricItem.position)
        ).all()
        assert len(items) == 4
        assert sum(i.weight_percent for i in items) == 100
        assert items[0].checks["files"][0]["present"] is True

        # A second pass leaves it alone rather than duplicating it.
        second = ensure_labs(db)
        db.commit()
        assert second["created"] == [] and second["skipped"] == ["log-triage"]
        assert (
            len(db.scalars(select(LabTemplate).where(LabTemplate.slug == "log-triage")).all())
            == 1
        )
    finally:
        db.close()


def test_the_bound_module_becomes_gated_once_the_lab_exists(client, student):
    """End to end: the lesson names log-triage, the catalog ships it with a
    published scheme, so the module stops being a button press."""
    me = client.get("/api/v1/auth/me", headers=student).json()
    db = SessionLocal()
    try:
        ensure_labs(db)
        db.commit()

        module = db.scalar(
            select(Module)
            .join(Path, Path.id == Module.path_id)
            .where(Path.slug == "soc-analyst", Module.lab_slug == "log-triage")
        )
        assert module is not None, "lesson 02 should be bound to log-triage"

        gate = status_for(db, module, me["id"])
        assert gate.lab_available is True
        assert gate.scheme_published is True
        assert gate.required is True
        assert gate.passed is False
        assert "Log Triage" in gate.reason
    finally:
        db.close()

    refused = client.post(
        f"/api/v1/academy/modules/{module.id}/complete", headers=student
    )
    assert refused.status_code == 403
    assert refused.json()["detail"]["error"] == "lab_not_passed"

    # Leave the shared database as we found it: a published scheme here would
    # gate this module for every later test in the session.
    db = SessionLocal()
    try:
        template = db.scalar(select(LabTemplate).where(LabTemplate.slug == "log-triage"))
        scheme_ids = select(GradingScheme.id).where(
            GradingScheme.lab_template_id == template.id
        )
        db.execute(delete(RubricItem).where(RubricItem.scheme_id.in_(scheme_ids)))
        db.execute(delete(GradingScheme).where(GradingScheme.lab_template_id == template.id))
        db.execute(delete(LabTemplate).where(LabTemplate.id == template.id))
        db.commit()
    finally:
        db.close()


def test_shipped_labs_stay_lightweight():
    """A lab ships a VM size, and that size is now what the hypervisor builds
    (ProxmoxProvider.provision sets cores/memory on the clone). Keeping the
    ceiling here means an accidental bump to a distro-sized default has to be
    argued for rather than merged."""
    for spec in CATALOG:
        if spec.kind != "vm":
            continue
        assert spec.vm_template, f"{spec.slug} is a vm lab with no template"
        assert spec.cpu <= 2, f"{spec.slug} asks for {spec.cpu} vCPU"
        assert spec.ram_gb <= 2, f"{spec.slug} asks for {spec.ram_gb} GB RAM"
