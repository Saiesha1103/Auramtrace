"""Authentication, roles, organisation isolation and the error envelope."""

from tests.conftest import MEAS, PASSWORD, auth


def test_register_login_me(client, admin):
    r = client.post("/api/v1/auth/login", json={"email": "ADMIN@aurumtrace-test.example.com", "password": PASSWORD})
    assert r.status_code == 200
    body = r.json()
    assert body["tokenType"] == "bearer" and body["expiresIn"] > 0
    assert body["user"]["role"] == "admin"
    me = client.get("/api/v1/auth/me", headers=auth(body["accessToken"])).json()
    assert me["email"] == "admin@aurumtrace-test.example.com"
    assert me["createdAt"].endswith("Z")
    assert "passwordHash" not in me and "password_hash" not in me


def test_wrong_password_and_missing_token(client, admin):
    r = client.post("/api/v1/auth/login", json={"email": "admin@aurumtrace-test.example.com", "password": "nope-nope-nope"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "invalid_credentials"
    r = client.get("/api/v1/karigars")
    assert r.status_code == 401
    assert r.json() == {"error": {"code": "unauthorized", "message": "Authentication required", "details": None}}
    r = client.get("/api/v1/karigars", headers=auth("not-a-jwt"))
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_token"


def test_duplicate_registration(client, admin):
    r = client.post("/api/v1/auth/register", json={"organisationName": "Again", "fullName": "X Y", "email": "admin@aurumtrace-test.example.com", "password": PASSWORD})
    assert r.status_code == 409 and r.json()["error"]["code"] == "email_taken"


def test_viewer_is_read_only(client, world, make_user):
    viewer = make_user("viewer")
    assert client.get("/api/v1/karigars", headers=viewer["h"]).status_code == 200
    r = client.post("/api/v1/karigars", headers=viewer["h"], json={"name": "Nope", "kind": "karigar"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "forbidden"
    assert r.json()["error"]["details"]["requiredRoles"] == ["admin", "manager"]
    r = client.post("/api/v1/lots", headers=viewer["h"], json={"grossWeightG": 1, "netWeightG": 1, "finenessPpt": 995, "measurement": MEAS})
    assert r.status_code == 403


def test_vault_operator_scope(client, world, make_user):
    op = make_user("vault_operator")
    # can receive lots and issue
    r = client.post("/api/v1/lots", headers=op["h"], json={"grossWeightG": 5, "netWeightG": 5, "finenessPpt": 995, "measurement": MEAS})
    assert r.status_code == 201
    r = client.post(f"/api/v1/lots/{world['lot']['id']}/issue", headers=op["h"], json={"jobId": world["job"]["id"], "karigarId": world["head"]["id"], "grossWeightG": 1, "netWeightG": 1, "measurement": MEAS})
    assert r.status_code == 201
    # but cannot reverse, create jobs, or manage users
    assert client.post(f"/api/v1/events/{r.json()['id']}/reverse", headers=op["h"], json={"reason": "testing permissions"}).status_code == 403
    assert client.post("/api/v1/jobs", headers=op["h"], json={"title": "X job", "karat": "22K", "pieces": 1, "dueDate": "2026-12-01"}).status_code == 403
    assert client.post("/api/v1/users", headers=op["h"], json={"email": "z@example.com", "fullName": "Zed", "role": "admin", "password": PASSWORD}).status_code == 403


def test_manager_cannot_manage_users(client, admin, make_user):
    mgr = make_user("manager")
    assert client.get("/api/v1/users", headers=mgr["h"]).status_code == 200
    assert client.post("/api/v1/users", headers=mgr["h"], json={"email": "z@example.com", "fullName": "Zed", "role": "viewer", "password": PASSWORD}).status_code == 403
    assert client.patch("/api/v1/organisations/me", headers=mgr["h"], json={"name": "Renamed"}).status_code == 403


def test_organisation_isolation(client, world):
    other = client.post("/api/v1/auth/register", json={"organisationName": "Other Org", "fullName": "Other Admin", "email": "other@aurumtrace-test.example.com", "password": PASSWORD}).json()
    h2 = auth(other["accessToken"])
    assert client.get(f"/api/v1/karigars/{world['karigar']['id']}", headers=h2).status_code == 404
    assert client.get(f"/api/v1/jobs/{world['job']['id']}", headers=h2).status_code == 404
    assert client.get("/api/v1/lots", headers=h2).json()["total"] == 0
    # cannot issue another org's lot, or to another org's karigar
    own_job = client.post("/api/v1/jobs", headers=h2, json={"title": "Own job", "karat": "22K", "pieces": 1, "dueDate": "2026-12-01"}).json()
    r = client.post(f"/api/v1/lots/{world['lot']['id']}/issue", headers=h2, json={"jobId": own_job["id"], "karigarId": world["karigar"]["id"], "grossWeightG": 1, "netWeightG": 1, "measurement": MEAS})
    assert r.status_code == 404


def test_inactive_user_rejected(client, admin, make_user):
    v = make_user("viewer")
    client.patch(f"/api/v1/users/{v['user']['id']}", headers=admin["h"], json={"isActive": False})
    assert client.get("/api/v1/auth/me", headers=v["h"]).status_code == 401
    r = client.post("/api/v1/auth/login", json={"email": "viewer@aurumtrace-test.example.com", "password": PASSWORD})
    assert r.status_code == 401 and r.json()["error"]["code"] == "account_inactive"


def test_admin_cannot_lock_self_out(client, admin):
    r = client.patch(f"/api/v1/users/{admin['user']['id']}", headers=admin["h"], json={"role": "viewer"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "self_lockout"


def test_registration_can_be_disabled(client, monkeypatch):
    from app import config

    monkeypatch.setattr(config.get_settings(), "allow_registration", False)
    r = client.post("/api/v1/auth/register", json={"organisationName": "Nope", "fullName": "No One", "email": "no@example.com", "password": PASSWORD})
    assert r.status_code == 403 and r.json()["error"]["code"] == "registration_disabled"


def test_validation_error_envelope(client, admin):
    r = client.post("/api/v1/lots", headers=admin["h"], json={"grossWeightG": 10, "netWeightG": 12, "finenessPpt": 1200, "measurement": MEAS})
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "validation_error"
    fields = {d["field"] for d in err["details"]}
    assert "finenessPpt" in fields
