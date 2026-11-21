import json
import sqlite3

import pytest

from tests.conftest import chat_body


def _row_count(client) -> int:
    conn = sqlite3.connect(client.app.state.db.path)
    try:
        return conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    finally:
        conn.close()


BAD_BODIES = [
    {"session_id": "s", "message": ""},
    {"session_id": "s", "message": "   \n\t "},
    {"session_id": "s"},
    {"message": "hi"},
    {"session_id": "", "message": "hi"},
    {"session_id": "   ", "message": "hi"},
    {"session_id": "x" * 129, "message": "hi"},
    {"session_id": "s", "message": "a" * 4001},
    {"session_id": "s", "message": 123},
    {"session_id": 7, "message": "hi"},
    {"session_id": "s", "message": "hi", "system_prompt": 5},
]


@pytest.mark.parametrize("body", BAD_BODIES)
async def test_invalid_payload_422_and_no_db_writes(client, provider, body):
    r = await client.post("/chat", json=body)
    assert r.status_code == 422
    assert "detail" in r.json()
    assert r.headers["content-type"].startswith("application/json")
    assert _row_count(client) == 0
    assert provider.calls == []


async def test_malformed_json_422(client):
    r = await client.post("/chat", content="{not json", headers={"Content-Type": "application/json"})
    assert r.status_code == 422
    assert "detail" in r.json()
    assert _row_count(client) == 0


async def test_boundary_values_accepted(client):
    assert (await client.post("/chat", json=chat_body("x" * 128, "a" * 4000))).status_code == 200
    padded = chat_body("  s-pad  ", "  hi  ")
    r = await client.post("/chat", json=padded)
    assert r.status_code == 200 and r.json()["session_id"] == "s-pad"


async def test_blank_system_prompt_is_ignored(client, provider):
    r = await client.post("/chat", json=chat_body("s-b", "hi", system_prompt="   "))
    assert r.status_code == 200
    assert provider.calls[-1][1][0]["content"] == "You are a helpful, concise AI assistant."


async def test_error_bodies_have_no_traces(client):
    r = await client.post("/chat", content=json.dumps({"session_id": "s", "message": ""}),
                          headers={"Content-Type": "application/json"})
    assert "Traceback" not in r.text and "<html" not in r.text.lower()
