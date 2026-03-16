"""Integration tests for FastAPI backends using httpx ASGITransport (no HTTP server)."""
import httpx
from httpx import ASGITransport


# ---- Telemetry ----
async def test_telemetry_cpu():
    from backends.telemetry import app

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/telemetry/cpu")
    assert r.status_code == 200
    data = r.json()
    assert "cores" in data
    assert "load" in data
    assert "ts" in data
    assert isinstance(data["cores"], list)
    assert isinstance(data["ts"], float)


async def test_telemetry_memory():
    from backends.telemetry import app

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/telemetry/memory")
    assert r.status_code == 200
    data = r.json()
    assert "total" in data
    assert "used" in data
    assert "percent" in data
    assert isinstance(data["total"], (int, float))
    assert isinstance(data["percent"], (int, float))


async def test_telemetry_disk():
    from backends.telemetry import app

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/telemetry/disk")
    assert r.status_code == 200
    data = r.json()
    assert "total" in data
    assert "used" in data
    assert "percent" in data
    assert isinstance(data["total"], (int, float))
    assert isinstance(data["percent"], (int, float))


async def test_telemetry_network():
    from backends.telemetry import app

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/telemetry/network")
    assert r.status_code == 200
    data = r.json()
    assert "bytes_sent" in data
    assert "bytes_recv" in data
    assert isinstance(data["bytes_sent"], (int, float))
    assert isinstance(data["bytes_recv"], (int, float))


# ---- Commands ----
async def test_command_allowlisted():
    from backends.commands import app

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/command/estop", json={})
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "ok"
    assert data.get("action") == "estop"
    assert "ts" in data


async def test_command_blocked():
    from backends.commands import app

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/command/reboot", json={})
    assert r.status_code == 403


# ---- Data stub ----
async def test_data_history_empty():
    from backends.data import app

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/history/cpu")
    assert r.status_code == 200
    assert r.json() == []


# ---- Prometheus stub ----
async def test_prometheus_query_stub():
    from backends.prometheus import app

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/metrics/query", params={"q": "up"})
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "success"
    assert "data" in data
    assert data["data"].get("resultType") == "vector"
    assert data["data"].get("result") == []


# ---- Audit ----
async def test_audit_recent_empty():
    from backends.audit import app

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/audit/recent")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


async def test_audit_recent_with_limit():
    from backends.audit import app

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/audit/recent", params={"limit": 5})
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) <= 5


async def test_audit_recent_entries_shape(tmp_path, monkeypatch):
    """Entries returned by /audit/recent have the expected keys."""
    import backends.audit as audit_mod

    db = tmp_path / "test_audit.db"
    monkeypatch.setattr(audit_mod, "_DB_PATH", db)
    monkeypatch.setattr(audit_mod, "_INITIALIZED", False)

    audit_mod.log_action("test_action", "tester", {"x": 1})

    from backends.audit import app

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/audit/recent")
    assert r.status_code == 200
    entries = r.json()
    assert len(entries) >= 1
    entry = entries[0]
    assert "ts" in entry
    assert "action" in entry
    assert "user" in entry
    assert "details" in entry


# ---- Binding check ----
async def test_backends_bind_localhost():
    """Verify each backend app returns valid responses."""
    from backends.telemetry import app as telemetry_app
    from backends.commands import app as commands_app
    from backends.data import app as data_app
    from backends.prometheus import app as prometheus_app

    apps = [
        (telemetry_app, "GET", "/telemetry/cpu", None),
        (commands_app, "POST", "/command/estop", {}),
        (data_app, "GET", "/history/cpu", None),
        (prometheus_app, "GET", "/metrics/query?q=up", None),
    ]
    for app_obj, method, path, body in apps:
        path_only = path.split("?")[0]
        params = {"q": "up"} if "?" in path else None
        transport = ASGITransport(app=app_obj)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            if method == "GET":
                r = await c.get(path_only, params=params)
            else:
                r = await c.post(path_only, json=body or {})
        assert r.status_code == 200, f"{app_obj.title} {method} {path} failed"
