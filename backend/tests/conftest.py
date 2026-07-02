"""Test harness: SQLite file DB per session (a temp file, so the app's
default engine wiring is exercised), local object storage in a temp dir,
and helper fixtures for authenticated principals of each role."""

import os
import sys
import tempfile
from pathlib import Path

import pytest

TMP = tempfile.mkdtemp(prefix="palestrix-test-")
FIXTURES = Path(__file__).resolve().parent / "fixtures"
os.environ["PALESTRIX_DATABASE_URL"] = f"sqlite:///{Path(TMP) / 'test.db'}"
os.environ["PALESTRIX_STORAGE_LOCAL_ROOT"] = str(Path(TMP) / "objects")
os.environ["PALESTRIX_SECRET_KEY"] = "test-secret-key-of-sufficient-length-0123456789"
os.environ["PALESTRIX_PLUGIN_PATHS"] = ",".join(
    str(FIXTURES / name) for name in ("crashy", "needy", "oldapi")
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from palestrix.db import Base, SessionLocal, engine  # noqa: E402
from palestrix.main import app  # noqa: E402
from palestrix.models import Role, Tenant, User  # noqa: E402
from palestrix.security import hash_password  # noqa: E402

PASSWORD = "test-password-123!"


@pytest.fixture(scope="session")
def client():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    db.add(
        Tenant(
            id="test-tenant", name="Test Tenant", instance_quota=2,
            network_cidr="10.9.0.0/24",
        )
    )
    pw = hash_password(PASSWORD)
    for name, handle, email, role in [
        ("Studious Student", "stud1", "stud1@example.edu", Role.student),
        ("Second Student", "stud2", "stud2@example.edu", Role.student),
        ("Testy Teacher", "teach1", "teach1@example.edu", Role.teacher),
        ("Adamant Admin", "admin1", "admin1@example.edu", Role.admin),
        ("Super User", "super1", "super1@example.edu", Role.superadmin),
    ]:
        db.add(
            User(
                name=name, handle=handle, email=email, role=role,
                tenant_id="test-tenant", password_hash=pw,
            )
        )
    db.commit()
    db.close()
    with TestClient(app) as c:
        yield c


def login(client: TestClient, email: str) -> dict:
    resp = client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture()
def student(client):
    return login(client, "stud1@example.edu")


@pytest.fixture()
def student2(client):
    return login(client, "stud2@example.edu")


@pytest.fixture()
def teacher(client):
    return login(client, "teach1@example.edu")


@pytest.fixture()
def admin(client):
    return login(client, "admin1@example.edu")


@pytest.fixture()
def superadmin(client):
    return login(client, "super1@example.edu")
