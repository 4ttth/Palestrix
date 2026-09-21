"""Lesson bodies and lab-gated completion.

Modules used to be titles with a button: completion was self-attestation and
the Palestras came anyway. These cover the two halves that changed -- lessons
shipped as repository content, and completion earned by passing a lab.
"""

import os
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, or_, select

from palestrix import academy_content_loader as content
from palestrix.academy_gate import status_for
from palestrix.db import SessionLocal
from palestrix.models import (
    GradeCheck,
    GradingScheme,
    Instance,
    InstanceLog,
    InstanceState,
    LabTemplate,
    Module,
    ModuleCompletion,
    Path,
)


# -- front matter and file resolution ------------------------------------------


def test_front_matter_is_parsed_off_the_body():
    lesson = content.parse(
        "---\n"
        "summary: One line.\n"
        "lab: log-triage\n"
        "pass: 70\n"
        "---\n\n"
        "# Heading\n\nBody text.\n"
    )
    assert lesson.summary == "One line."
    assert lesson.lab_slug == "log-triage"
    assert lesson.pass_percent == 70
    assert lesson.body.startswith("# Heading")
    assert "summary:" not in lesson.body
    assert not lesson.empty


def test_a_file_without_front_matter_is_all_body():
    lesson = content.parse("# Just a heading\n\nand text.\n")
    assert lesson.summary == ""
    assert lesson.lab_slug is None
    assert lesson.pass_percent == content.DEFAULT_PASS_PERCENT
    assert lesson.body.startswith("# Just a heading")


def test_pass_percent_is_clamped_and_ignores_nonsense():
    assert content.parse("---\npass: 0\n---\nx").pass_percent == content.DEFAULT_PASS_PERCENT
    assert (
        content.parse("---\npass: 500\n---\nx").pass_percent
        == content.DEFAULT_PASS_PERCENT
    )
    assert content.parse("---\npass: soon\n---\nx").pass_percent == content.DEFAULT_PASS_PERCENT


def test_filenames_follow_position_and_slug():
    assert content.filename_for(0, "The SOC shift: alerts, queues, and escalation") == (
        "01-the-soc-shift-alerts-queues-and-escalation.md"
    )
    assert content.filename_for(11, "Writing the incident report") == (
        "12-writing-the-incident-report.md"
    )


def test_a_module_with_no_file_is_not_an_error():
    lesson = content.load("soc-analyst", 99, "A module nobody has written")
    assert lesson.empty and lesson.body == ""


def test_shipped_lessons_load_and_declare_what_they_need():
    """The bodies in academy_content/ must actually resolve; a renamed title
    silently orphans its file otherwise."""
    from palestrix.academy_catalog import CATALOG

    written = 0
    for spec in CATALOG:
        for position, spec_module in enumerate(spec.modules):
            lesson = content.load(spec.slug, position, spec_module.title)
            if lesson.empty:
                continue
            written += 1
            assert lesson.summary, f"{spec.slug}/{spec_module.title} has no summary"
    assert written >= 3, "expected the shipped exemplar lessons to resolve"


def test_content_root_holds_no_orphans():
    """Every .md under academy_content/ belongs to a module in the catalog."""
    from palestrix.academy_catalog import CATALOG

    expected = {
        (spec.slug, content.filename_for(i, m.title))
        for spec in CATALOG
        for i, m in enumerate(spec.modules)
    }
    for path_slug in sorted(os.listdir(content.CONTENT_ROOT)):
        directory = os.path.join(content.CONTENT_ROOT, path_slug)
        if not os.path.isdir(directory):
            continue
        for filename in sorted(os.listdir(directory)):
            if not filename.endswith(".md"):
                continue
            assert (path_slug, filename) in expected, (
                f"{path_slug}/{filename} matches no module -- a title was renamed?"
            )


# -- the catalog publishes them ------------------------------------------------


def test_catalog_publishes_bodies_into_the_database(client):
    db = SessionLocal()
    try:
        module = db.scalar(
            select(Module)
            .join(Path, Path.id == Module.path_id)
            .where(Path.slug == "soc-analyst", Module.position == 0)
        )
        assert module is not None
        assert module.body.strip(), "startup should have loaded the lesson body"
        assert module.summary
    finally:
        db.close()


def test_reading_a_module_returns_its_body(client, student):
    paths = client.get("/api/v1/academy/paths", headers=student).json()
    slug = next(p["slug"] for p in paths if p["slug"] == "soc-analyst")
    modules = client.get(f"/api/v1/academy/paths/{slug}/modules", headers=student).json()

    first = modules[0]
    assert first["has_body"] is True
    assert first["summary"]

    detail = client.get(f"/api/v1/academy/modules/{first['id']}", headers=student).json()
    assert detail["body"].startswith("#")
    assert detail["completed"] is False
    assert detail["locked_reason"] == ""       # no lab bound, nothing to block it


def test_reading_an_unknown_module_is_404(client, student):
    assert client.get("/api/v1/academy/modules/nope", headers=student).status_code == 404


# -- the gate ------------------------------------------------------------------


@pytest.fixture()
def gated_module(request):
    """A module bound to a lab, named uniquely per test.

    The suite shares one database across the session, so a fixed slug makes
    the second test that uses it collide on lab_templates.slug rather than
    exercise the gate.
    """
    tag = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        path = db.scalar(select(Path).where(Path.slug == "soc-analyst"))
        module = Module(
            path_id=path.id,
            title=f"Gate fixture {tag}",
            position=900,
            palestras_award=10,
            body="# Gate fixture",
            summary="fixture",
            lab_slug=f"gate-lab-{tag}",
            pass_percent=80,
        )
        db.add(module)
        db.flush()
        module_id = module.id
        db.commit()
    finally:
        db.close()

    # The slug travels with the id so a test can build the matching template.
    yield SimpleNamespace(id=module_id, lab_slug=f"gate-lab-{tag}")

    # Everything these tests create lands in the session-wide database, and a
    # leftover instance in an active state holds tenant CPU/RAM that every
    # later launch test needs. Unwind in FK order.
    db = SessionLocal()
    try:
        template = db.scalar(
            select(LabTemplate).where(LabTemplate.slug == f"gate-lab-{tag}")
        )
        if template is not None:
            scheme_ids = select(GradingScheme.id).where(
                GradingScheme.lab_template_id == template.id
            )
            instance_ids = select(Instance.id).where(
                Instance.template_id == template.id
            )
            db.execute(
                delete(GradeCheck).where(
                    or_(
                        GradeCheck.instance_id.in_(instance_ids),
                        GradeCheck.scheme_id.in_(scheme_ids),
                    )
                )
            )
            db.execute(delete(InstanceLog).where(InstanceLog.instance_id.in_(instance_ids)))
            db.execute(delete(Instance).where(Instance.template_id == template.id))
            db.execute(delete(GradingScheme).where(GradingScheme.lab_template_id == template.id))
            db.execute(delete(LabTemplate).where(LabTemplate.id == template.id))
        db.execute(delete(ModuleCompletion).where(ModuleCompletion.module_id == module_id))
        db.execute(delete(Module).where(Module.id == module_id))
        db.commit()
    finally:
        db.close()


def _make_lab(db, owner_id, slug: str, *, published: bool) -> LabTemplate:
    template = LabTemplate(slug=slug, title="Gate Lab", owner_id=owner_id)
    db.add(template)
    db.flush()
    db.add(
        GradingScheme(
            lab_template_id=template.id,
            kind="diff",
            status="published" if published else "draft",
            created_by=owner_id,
        )
    )
    db.flush()
    return template


def test_an_unimported_lab_does_not_lock_the_student_out(client, student, gated_module):
    """The catalog names a lab this deployment has not imported. Falling back
    to the honour system beats blocking content that exists."""
    db = SessionLocal()
    try:
        module = db.get(Module, gated_module.id)
        me = client.get("/api/v1/auth/me", headers=student).json()
        gate = status_for(db, module, me["id"])
        assert gate.lab_available is False
        assert gate.required is False
        assert gate.passed is True
    finally:
        db.close()


def test_a_draft_scheme_does_not_gate(client, student, gated_module):
    """Draft rubrics have editable weights and grading turned off, so
    enforcing against one blocks students on a lab nobody can pass."""
    db = SessionLocal()
    try:
        me = client.get("/api/v1/auth/me", headers=student).json()
        _make_lab(db, me["id"], gated_module.lab_slug, published=False)
        db.commit()
        gate = status_for(db, db.get(Module, gated_module.id), me["id"])
        assert gate.lab_available is True
        assert gate.scheme_published is False
        assert gate.required is False
    finally:
        db.close()


def test_published_scheme_gates_until_the_check_passes(client, student, gated_module):
    me = client.get("/api/v1/auth/me", headers=student).json()
    db = SessionLocal()
    try:
        template = _make_lab(db, me["id"], gated_module.lab_slug, published=True)
        scheme = db.scalar(
            select(GradingScheme).where(GradingScheme.lab_template_id == template.id)
        )
        db.commit()

        gate = status_for(db, db.get(Module, gated_module.id), me["id"])
        assert gate.required is True and gate.passed is False
        assert gate.best_percent is None
        assert "pass the automated check" in gate.reason

        # Completion is refused while unpassed.
        refused = client.post(
            f"/api/v1/academy/modules/{gated_module.id}/complete", headers=student
        )
        assert refused.status_code == 403
        assert refused.json()["detail"]["error"] == "lab_not_passed"

        # A failing run is still not a pass.
        instance = Instance(
            id=f"lab-{uuid.uuid4().hex[:8]}",
            template_id=template.id,
            owner_id=me["id"],
            tenant_id=me["tenant_id"],
            state=InstanceState.running,
        )
        db.add(instance)
        db.flush()
        db.add(
            GradeCheck(
                scheme_id=scheme.id,
                instance_id=instance.id,
                user_id=me["id"],
                total_percent=55,
            )
        )
        db.commit()

        gate = status_for(db, db.get(Module, gated_module.id), me["id"])
        assert gate.passed is False and gate.best_percent == 55
        assert "55%" in gate.reason
        assert (
            client.post(
                f"/api/v1/academy/modules/{gated_module.id}/complete", headers=student
            ).status_code
            == 403
        )

        # A passing run opens it.
        db.add(
            GradeCheck(
                scheme_id=scheme.id,
                instance_id=instance.id,
                user_id=me["id"],
                total_percent=88,
            )
        )
        db.commit()

        gate = status_for(db, db.get(Module, gated_module.id), me["id"])
        assert gate.passed is True and gate.best_percent == 88
        assert gate.reason == ""
    finally:
        db.close()

    allowed = client.post(
        f"/api/v1/academy/modules/{gated_module.id}/complete", headers=student
    )
    assert allowed.status_code == 201
    assert allowed.json()["completed"] is True


def test_another_students_pass_does_not_count(client, student, student2, gated_module):
    """The grade is per user: one student clearing the lab must not complete
    the module for everyone."""
    me = client.get("/api/v1/auth/me", headers=student).json()
    other = client.get("/api/v1/auth/me", headers=student2).json()

    db = SessionLocal()
    try:
        template = _make_lab(db, me["id"], gated_module.lab_slug, published=True)
        scheme = db.scalar(
            select(GradingScheme).where(GradingScheme.lab_template_id == template.id)
        )
        instance = Instance(
            id=f"lab-{uuid.uuid4().hex[:8]}",
            template_id=template.id,
            owner_id=me["id"],
            tenant_id=me["tenant_id"],
            state=InstanceState.running,
        )
        db.add(instance)
        db.flush()
        # The first student clears it comfortably.
        db.add(
            GradeCheck(
                scheme_id=scheme.id,
                instance_id=instance.id,
                user_id=me["id"],
                total_percent=95,
            )
        )
        db.commit()

        assert status_for(db, db.get(Module, gated_module.id), me["id"]).passed is True

        gate = status_for(db, db.get(Module, gated_module.id), other["id"])
        assert gate.required is True
        assert gate.passed is False
        assert gate.best_percent is None
    finally:
        db.close()

    refused = client.post(
        f"/api/v1/academy/modules/{gated_module.id}/complete", headers=student2
    )
    assert refused.status_code == 403
