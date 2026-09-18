"""The academy catalog shipped in the repository (palestrix/academy_catalog.py).

The app applies it during startup, so the `client` fixture alone proves the
four paths reach a fresh database. The rest covers re-running it against a
database that already holds some of the content.
"""

from sqlalchemy import select

from palestrix.academy_catalog import CATALOG, CatalogModule, CatalogPath, ensure_catalog
from palestrix.db import SessionLocal
from palestrix.models import Module, Path

# The counts the landing page advertises (app/(marketing)/page.tsx).
ADVERTISED = {
    "soc-analyst": ("SOC Analyst", 14),
    "web-exploitation": ("Web Exploitation", 12),
    "network-defense": ("Network Defense", 10),
    "digital-forensics": ("Digital Forensics", 11),
}


def test_catalog_matches_the_landing_page_preview():
    assert {p.slug: (p.title, len(p.modules)) for p in CATALOG} == ADVERTISED


def test_startup_publishes_every_path_with_its_modules(client, student):
    paths = {p["slug"]: p for p in client.get("/api/v1/academy/paths", headers=student).json()}
    for slug, (title, count) in ADVERTISED.items():
        assert paths[slug]["title"] == title
        modules = client.get(
            f"/api/v1/academy/paths/{slug}/modules", headers=student
        ).json()
        assert len(modules) == count
        assert [m["position"] for m in modules] == list(range(count))
        assert all(m["palestras_award"] > 0 for m in modules)
        assert not any(m["completed"] for m in modules)


def test_reapplying_the_catalog_changes_nothing(client):
    db = SessionLocal()
    try:
        before = db.scalar(select(Module.id).where(Module.title == "Windows registry forensics"))
        report = ensure_catalog(db)
        db.commit()
        assert report["paths_created"] == []
        assert report["modules_created"] == []
        assert report["modules_renumbered"] == 0
        after = db.scalar(select(Module.id).where(Module.title == "Windows registry forensics"))
        assert after == before  # rows are adopted, never recreated
    finally:
        db.close()


def test_existing_modules_are_adopted_renumbered_and_teacher_work_survives(client):
    """A path seeded by an earlier release holds a subset of the catalog's
    modules, in the wrong order, plus one a teacher added. Applying the
    catalog fills the gaps and reorders without touching either row's id."""
    spec = CatalogPath(
        slug="catalog-test-path",
        title="Catalog Test Path",
        hours=9,
        modules=(
            CatalogModule("First", 10),
            CatalogModule("Second", 20),
            CatalogModule("Third", 30),
        ),
    )
    db = SessionLocal()
    try:
        path = Path(slug="catalog-test-path", title="Stale Title", hours=1)
        db.add(path)
        db.flush()
        third = Module(path_id=path.id, title="Third", position=0, palestras_award=30)
        teachers = Module(path_id=path.id, title="Teacher's own", position=1, palestras_award=5)
        db.add_all([third, teachers])
        db.commit()
        third_id, teacher_id = third.id, teachers.id

        report = ensure_catalog(db, (spec,))
        db.commit()

        assert report["paths_created"] == []
        assert sorted(report["modules_created"]) == [
            "catalog-test-path/First",
            "catalog-test-path/Second",
        ]

        path = db.scalar(select(Path).where(Path.slug == "catalog-test-path"))
        assert (path.title, path.hours) == ("Catalog Test Path", 9)
        modules = db.scalars(
            select(Module).where(Module.path_id == path.id).order_by(Module.position)
        ).all()
        assert [m.title for m in modules] == ["First", "Second", "Third", "Teacher's own"]
        assert modules[2].id == third_id  # adopted, not duplicated
        assert modules[3].id == teacher_id  # teacher's module kept, pushed after
    finally:
        db.close()
