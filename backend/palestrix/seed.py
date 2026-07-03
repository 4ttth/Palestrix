"""Development seed: demo tenant, users, course, path, event, and templates
mirroring the frontend's lib/mock.ts so the two halves tell one story.

Run:  python -m palestrix.seed
Idempotent: safe to re-run; existing rows are left alone.

DEMO CREDENTIALS, DEVELOPMENT ONLY. Every account's password is
"palestrix-dev-only!" and must never exist outside a local machine.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from .db import Base, SessionLocal, engine
from .models import (
    Challenge,
    Course,
    CtfEvent,
    Enrollment,
    LabTemplate,
    LedgerEntry,
    Module,
    Path,
    Role,
    Streak,
    Tenant,
    User,
    Vote,
    Writeup,
    utcnow,
)
from .security import hash_password, sha256_hex

PASSWORD = "palestrix-dev-only!"

USERS = [
    ("Rafaela Almazan", "rafalmz", "rafaela@example.edu", Role.student),
    ("Amihan Buenaventura", "amihan", "amihan@example.edu", Role.student),
    ("Gabriel Locsin", "gab_lockpick", "gabriel@example.edu", Role.student),
    ("Teodoro Dela Cruz", "sir.delacruz", "delacruz@example.edu", Role.teacher),
    ("Odessa Pineda", "admin.ops", "odessa@example.edu", Role.admin),
    ("Root Account", "root", "root@example.edu", Role.superadmin),
]


def seed() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.scalar(select(Tenant).where(Tenant.id == "hau-bscs-3a")) is None:
            db.add(
                Tenant(
                    id="hau-bscs-3a",
                    name="HAU BSCS 3A",
                    instance_quota=3,
                    network_cidr="10.24.7.0/24",
                )
            )

        pw = hash_password(PASSWORD)
        users: dict[str, User] = {}
        for name, handle, email, role in USERS:
            user = db.scalar(select(User).where(User.handle == handle))
            if user is None:
                user = User(
                    name=name,
                    handle=handle,
                    email=email,
                    role=role,
                    tenant_id="hau-bscs-3a",
                    password_hash=pw,
                )
                db.add(user)
            users[handle] = user
        db.flush()

        # Starting Palestras so extend/hint flows are testable immediately.
        for handle in ("rafalmz", "amihan", "gab_lockpick"):
            if not db.scalar(
                select(LedgerEntry).where(LedgerEntry.user_id == users[handle].id)
            ):
                db.add(
                    LedgerEntry(
                        user_id=users[handle].id,
                        delta=500,
                        reason="seed.grant",
                        ref="dev",
                    )
                )

        if db.scalar(select(Course)) is None:
            course = Course(
                code="CS 3712",
                title="Defensive Operations 201",
                section="BSCS 3A",
                tenant_id="hau-bscs-3a",
                teacher_id=users["sir.delacruz"].id,
            )
            db.add(course)
            db.flush()
            for handle in ("rafalmz", "amihan", "gab_lockpick"):
                db.add(Enrollment(course_id=course.id, user_id=users[handle].id))

        if db.scalar(select(Path)) is None:
            path = Path(slug="soc-analyst", title="SOC Analyst", hours=31)
            db.add(path)
            db.flush()
            for i, (title, award) in enumerate(
                [
                    ("Reading auth logs at speed", 40),
                    ("Sigma rules from scratch", 55),
                    ("Lateral movement patterns", 60),
                    ("Building a triage runbook", 45),
                    ("Capstone: 48-hour incident", 120),
                ]
            ):
                db.add(
                    Module(
                        path_id=path.id, title=title, position=i, palestras_award=award
                    )
                )

        if db.scalar(select(LabTemplate)) is None:
            db.add(
                LabTemplate(
                    slug="log-triage:1.4",
                    title="Blue Team: Log Triage Under Fire",
                    kind="container",
                    access_mode="no-gui",
                    ttl_minutes_default=90,
                    ttl_minutes_max=240,
                    archive_key="lab-archives/templates/log-triage_1.4/bundle.tar.gz",
                    owner_id=users["sir.delacruz"].id,
                )
            )

        # A demo streak so the dashboard's streak card and the weekly-checkpoint
        # rule are visible immediately (mirrors lib/mock.ts: 11-day streak).
        if db.scalar(select(Streak)) is None:
            today = utcnow().date()
            db.add(
                Streak(
                    user_id=users["rafalmz"].id,
                    current_days=11,
                    longest_days=11,
                    last_active_on=today,
                    weeks_paid=1,  # 11 // 7 == 1 checkpoint already paid
                )
            )
            db.add(
                Streak(
                    user_id=users["amihan"].id,
                    current_days=4,
                    longest_days=9,
                    last_active_on=today,
                    weeks_paid=0,
                )
            )

        # Published writeups with votes so community score, the community
        # leaderboard, and public profiles have real data (mirrors lib/mock.ts).
        if db.scalar(select(Writeup)) is None:
            demo_writeups = [
                (
                    "amihan",
                    "Repeating Pad: XOR is not a vault",
                    ["crypto", "xor"],
                    ("rafalmz", "gab_lockpick", "sir.delacruz"),
                ),
                (
                    "rafalmz",
                    "Log triage: a 15-minute runbook",
                    ["blue-team", "siem"],
                    ("amihan", "gab_lockpick"),
                ),
            ]
            for author, title, tags, voters in demo_writeups:
                writeup = Writeup(
                    author_id=users[author].id,
                    title=title,
                    body_md=f"# {title}\n\nSeeded writeup for local development.",
                    tags=tags,
                    published=True,
                )
                db.add(writeup)
                db.flush()
                for voter in voters:
                    db.add(
                        Vote(
                            writeup_id=writeup.id,
                            user_id=users[voter].id,
                            value=1,
                        )
                    )

        if db.scalar(select(CtfEvent)) is None:
            now = datetime.now(timezone.utc)
            event = CtfEvent(
                title="CLCTF 2026 Qualifier Round 2",
                starts_at=now - timedelta(hours=1),
                ends_at=now + timedelta(hours=5),
                tenant_id="hau-bscs-3a",
                created_by=users["sir.delacruz"].id,
            )
            db.add(event)
            db.flush()
            for title, category, points, flag, award in [
                ("Cookie Monster's Bakery", "Web", 250, "CLCTF{s3ss10n_cruMbs}", 100),
                ("Repeating Pad", "Crypto", 200, "CLCTF{x0r_is_n0t_a_vault}", 80),
                ("Geoguesser: Pampanga", "OSINT", 150, "CLCTF{sisig_capital}", 60),
            ]:
                db.add(
                    Challenge(
                        event_id=event.id,
                        title=title,
                        category=category,
                        points=points,
                        flag_hash=sha256_hex(flag),
                        palestras_award=award,
                        created_by=users["sir.delacruz"].id,
                    )
                )

        # A finished sandbox analysis so the /sandbox surface renders real data
        # immediately. The sample is the EICAR test file — the harmless,
        # industry-standard anti-malware test artifact, not real malware — so
        # the demo detonator reaches a definitive verdict with zero risk.
        from .models import SandboxRun
        from .sandbox import submit_run
        from .sandbox.analysis import EICAR

        if db.scalar(select(SandboxRun)) is None:
            submit_run(
                db,
                submitter_id=users["rafalmz"].id,
                tenant_id="hau-bscs-3a",
                filename="eicar.com.txt",
                data=EICAR.encode(),
                media_type="text/plain",
            )

        db.commit()
        print("Seed complete. Demo login: rafaela@example.edu / " + PASSWORD)
    finally:
        db.close()


if __name__ == "__main__":
    seed()
