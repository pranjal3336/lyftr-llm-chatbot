from tests.conftest import running_app


async def test_health_ok(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "keys_configured": 2, "cache_enabled": True}


async def test_health_503_when_database_unavailable(client, monkeypatch):
    async def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(client.app.state.db, "check", boom)
    r = await client.get("/health")
    assert r.status_code == 503
    assert "detail" in r.json()


async def test_health_503_with_fewer_than_two_keys(tmp_settings, provider):
    async with running_app(tmp_settings(llm_api_keys="only-one")) as c:
        r = await c.get("/health")
        assert r.status_code == 503
        assert "detail" in r.json()


async def test_health_reports_cache_disabled(tmp_settings, provider):
    async with running_app(tmp_settings(cache_enabled=False)) as c:
        assert (await c.get("/health")).json()["cache_enabled"] is False


async def test_cors_preflight_allows_frontend_origin_and_sim_header(client):
    r = await client.options(
        "/chat",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-simulate-failure",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "x-simulate-failure" in r.headers["access-control-allow-headers"].lower()
