"""Test fixtures.

Database: SQLite (temp file) by default; set AURUM_TEST_DATABASE_URL to run against PostgreSQL, e.g.
    AURUM_TEST_DATABASE_URL=postgresql+psycopg://aurumtrace:aurumtrace_dev@localhost:5433/aurumtrace_test
Every test gets freshly created tables (append-only triggers included).
"""

import os
import tempfile
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("AURUM_ENV", "test")
os.environ.setdefault("AURUM_JWT_SECRET", "test-secret-for-pytest-only-0123456789")

from app import models  # noqa: E402,F401  (registers triggers)
from app.database import Base, get_db, make_engine  # noqa: E402
from app.main import create_app  # noqa: E402

_tmp = tempfile.mkdtemp(prefix="aurum-test-")
PG_URL = os.environ.get("AURUM_TEST_DATABASE_URL")

PASSWORD = "Correct-Horse-2026"  # synthetic test credential


@pytest.fixture(scope="session")
def _pg_engine():
    if not PG_URL:
        yield None
        return
    eng = make_engine(PG_URL)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture()
def engine(_pg_engine, request):
    """Fresh schema per test. PostgreSQL: drop/create on the shared test DB.
    SQLite: a new database file per test (SQLite can't DROP tables holding self-referencing rows)."""
    if _pg_engine is not None:
        Base.metadata.drop_all(_pg_engine)
        Base.metadata.create_all(_pg_engine)
        yield _pg_engine
        return
    eng = make_engine(f"sqlite:///{_tmp}/{request.node.name[:60].replace('[', '_').replace(']', '')}-{id(request)}.db")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def SessionLocal(engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture()
def db(SessionLocal) -> Iterator[Session]:
    s = SessionLocal()
    yield s
    s.rollback()
    s.close()


@pytest.fixture()
def client(SessionLocal) -> Iterator[TestClient]:
    app = create_app()

    def _get_db():
        s = SessionLocal()
        try:
            yield s
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app) as c:
        yield c


# ------------------------------------------------------------------ helpers


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def admin(client) -> dict:
    r = client.post("/api/v1/auth/register", json={"organisationName": "Test Jewellers (synthetic)", "fullName": "Test Admin", "email": "admin@aurumtrace-test.example.com", "password": PASSWORD})
    assert r.status_code == 201, r.text
    body = r.json()
    return {"token": body["accessToken"], "user": body["user"], "h": auth(body["accessToken"])}


@pytest.fixture()
def make_user(client, admin):
    def _make(role: str, email: str | None = None) -> dict:
        email = email or f"{role}@aurumtrace-test.example.com"
        r = client.post("/api/v1/users", headers=admin["h"], json={"email": email, "fullName": f"Test {role}", "role": role, "password": PASSWORD})
        assert r.status_code == 201, r.text
        t = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).json()["accessToken"]
        return {"user": r.json(), "h": auth(t)}

    return _make


MEAS = {"scaleId": "SC-01", "operatorName": "Vault desk", "method": "manual"}


@pytest.fixture()
def world(client, admin) -> dict:
    """A head karigar, a karigar in their team, a job and a 30.151 g lot @ 995."""
    h = admin["h"]
    head = client.post("/api/v1/karigars", headers=h, json={"code": "K-02", "name": "Farida Shaikh", "kind": "head_karigar", "unit": "Unit B"}).json()
    kar = client.post("/api/v1/karigars", headers=h, json={"code": "K-07", "name": "Anil Verma", "kind": "karigar", "headKarigarId": head["id"]}).json()
    job = client.post("/api/v1/jobs", headers=h, json={"code": "J-1182", "title": "Temple bangles", "karat": "22K", "pieces": 6, "lossAllowancePct": 1.2, "headKarigarId": head["id"], "dueDate": "2026-11-12"}).json()
    lot = client.post("/api/v1/lots", headers=h, json={"code": "L-3301", "source": "Bar 995 · B-792", "grossWeightG": 30.151, "netWeightG": 30.151, "finenessPpt": 995, "measurement": MEAS}).json()
    return {"h": h, "head": head, "karigar": kar, "job": job, "lot": lot}


def issue(client, w: dict, net: float = 30.151, gross: float | None = None, karigar_id: str | None = None, headers: dict | None = None):
    return client.post(
        f"/api/v1/lots/{w['lot']['id']}/issue",
        headers=headers or w["h"],
        json={"jobId": w["job"]["id"], "karigarId": karigar_id or w["head"]["id"], "grossWeightG": gross if gross is not None else net, "netWeightG": net, "measurement": MEAS, "challanRef": "JWC-26-3301"},
    )
