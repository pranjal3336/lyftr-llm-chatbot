from tests.conftest import chat_body, running_app


async def test_history_oldest_first_without_system_prompt(client):
    await client.post("/chat", json=chat_body("s-1", "first", system_prompt="SECRET SYSTEM"))
    await client.post("/chat", json=chat_body("s-1", "second"))
    r = await client.get("/sessions/s-1/messages")
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == "s-1"
    msgs = body["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]
    assert [m["content"] for m in msgs if m["role"] == "user"] == ["first", "second"]
    assert "SECRET SYSTEM" not in r.text
    for m in msgs:
        if m["role"] == "user":
            assert "metadata" not in m
        else:
            md = m["metadata"]
            assert md["resolution_source"] in {"LIVE_INFERENCE", "LLM_CACHE"}
            assert isinstance(md["input_tokens"], int) and isinstance(md["output_tokens"], int)


async def test_sessions_are_isolated(client):
    await client.post("/chat", json=chat_body("s-1", "alpha"))
    await client.post("/chat", json=chat_body("s-2", "beta"))
    m1 = (await client.get("/sessions/s-1/messages")).json()["messages"]
    m2 = (await client.get("/sessions/s-2/messages")).json()["messages"]
    assert m1[0]["content"] == "alpha" and m2[0]["content"] == "beta"
    assert "beta" not in str(m1) and "alpha" not in str(m2)


async def test_unknown_session_404(client):
    r = await client.get("/sessions/missing/messages")
    assert r.status_code == 404
    assert r.json() == {"detail": "session not found"}


async def test_unknown_route_returns_json_error(client):
    r = await client.get("/nope")
    assert r.status_code == 404
    assert "detail" in r.json()


async def test_history_survives_restart(tmp_settings, provider):
    settings = tmp_settings()
    async with running_app(settings) as c1:
        await c1.post("/chat", json=chat_body("s-persist", "remember me"))
    # New app instance, same SQLite file (simulates container restart with the volume kept).
    async with running_app(settings) as c2:
        r = await c2.get("/sessions/s-persist/messages")
        assert r.status_code == 200
        msgs = r.json()["messages"]
        assert msgs[0] == {"role": "user", "content": "remember me"}
        assert msgs[1]["role"] == "assistant"
        # Conversation context is also restored for the LLM.
        await c2.post("/chat", json=chat_body("s-persist", "and now?"))
        assert provider.calls[-1][1][1]["content"] == "remember me"


async def test_database_url_parsing_and_dir_creation(tmp_path):
    from app.db.database import Database, parse_database_url

    assert parse_database_url("sqlite:////data/app.db") == "/data/app.db"
    assert parse_database_url("sqlite:///./data/app.db") == "./data/app.db"
    target = tmp_path / "nested" / "dir" / "app.db"
    db = Database(f"sqlite:///{target}")
    await db.init()
    assert target.exists()
