import logging

import pytest

from tests.conftest import chat_body, running_app

SIM = "X-Simulate-Failure"


async def _history_missing(client, session_id):
    return (await client.get(f"/sessions/{session_id}/messages")).status_code == 404


@pytest.mark.parametrize("behavior", [429, "quota", 500, 503])
async def test_real_key_failover(client, provider, behavior):
    provider.behaviors["k1"] = behavior
    r = await client.post("/chat", json=chat_body("s-f", "hello"))
    assert r.status_code == 200
    meta = r.json()["metadata"]
    assert meta["resolution_source"] == "LIVE_INFERENCE"
    assert meta["key_id"] == "key_2" and meta["fallback_attempts"] == 1
    assert r.json()["reply"]


async def test_key1_recovers_after_real_failure(client, provider):
    provider.behaviors["k1"] = 429
    await client.post("/chat", json=chat_body("s-1", "one"))
    provider.behaviors.clear()
    r = (await client.post("/chat", json=chat_body("s-2", "two"))).json()
    assert r["metadata"]["key_id"] == "key_1"  # no sticky cooldown


async def test_all_real_keys_fail_503_and_nothing_saved(client, provider):
    provider.behaviors.update({"k1": 429, "k2": 503})
    r = await client.post("/chat", json=chat_body("s-x", "hello"))
    assert r.status_code == 503
    assert r.json() == {"detail": "all providers unavailable"}
    assert await _history_missing(client, "s-x")


@pytest.mark.parametrize("status", [429, 500, 502, 503])
async def test_sim_partial_failover(client, provider, status):
    r = await client.post(
        "/chat", json=chat_body("s-sim", "hello"), headers={SIM: f"key_1={status}"}
    )
    assert r.status_code == 200
    meta = r.json()["metadata"]
    assert meta["resolution_source"] == "LIVE_INFERENCE"
    assert meta["key_id"] == "key_2" and meta["fallback_attempts"] == 1
    assert r.json()["reply"].startswith("reply to:")  # a real answer, not an error wrapped in 200
    assert provider.calls_for("k1") == 0  # simulated: key_1's provider is never hit


async def test_sim_bypasses_cache_and_is_request_scoped(client, provider):
    first = (await client.post("/chat", json=chat_body("s-1", "cached?"))).json()
    assert first["metadata"]["key_id"] == "key_1"
    # Same prompt is now cached, but the simulation header must force a live failover.
    sim = (
        await client.post("/chat", json=chat_body("s-2", "cached?"), headers={SIM: "key_1=429"})
    ).json()
    assert sim["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    assert sim["metadata"]["key_id"] == "key_2"
    assert sim["metadata"]["fallback_attempts"] == 1
    # Next call without the header: key_1 is healthy again and the original cache entry is intact.
    after = (await client.post("/chat", json=chat_body("s-3", "cached?"))).json()
    assert after["metadata"]["resolution_source"] == "LLM_CACHE"
    fresh = (await client.post("/chat", json=chat_body("s-4", "brand new"))).json()
    assert fresh["metadata"]["key_id"] == "key_1" and fresh["metadata"]["fallback_attempts"] == 0


async def test_sim_does_not_store_or_serve_cache(client, provider):
    await client.post("/chat", json=chat_body("s-1", "q"), headers={SIM: "key_1=500"})
    r = (await client.post("/chat", json=chat_body("s-2", "q"))).json()
    assert r["metadata"]["resolution_source"] == "LIVE_INFERENCE"  # sim response was not cached


@pytest.mark.parametrize("header", ["*=429", "key_1=429,key_2=500", "*=503"])
async def test_sim_total_failure_503_and_nothing_saved(client, provider, header):
    r = await client.post("/chat", json=chat_body("s-t", "hello"), headers={SIM: header})
    assert r.status_code == 503
    assert r.json() == {"detail": "all providers unavailable"}
    assert await _history_missing(client, "s-t")
    assert provider.calls == []


async def test_sim_with_real_failure_on_remaining_key(client, provider):
    provider.behaviors["k2"] = 500
    r = await client.post("/chat", json=chat_body("s-m", "hi"), headers={SIM: "key_1=429"})
    assert r.status_code == 503
    assert await _history_missing(client, "s-m")


async def test_sim_header_ignored_when_flag_disabled(tmp_settings, provider):
    async with running_app(tmp_settings(enable_failure_simulation=False)) as c:
        r = await c.post("/chat", json=chat_body("s-d", "hello"), headers={SIM: "*=429"})
        assert r.status_code == 200
        assert r.json()["metadata"]["key_id"] == "key_1"


async def test_sim_header_garbage_is_ignored(client):
    r = await client.post(
        "/chat", json=chat_body("s-g", "hello"), headers={SIM: "key_1=418,foo,key_9=429,=="}
    )
    assert r.status_code == 200
    assert r.json()["metadata"]["key_id"] == "key_1"


async def test_three_key_pool_chain(tmp_settings, provider):
    async with running_app(tmp_settings(llm_api_keys="k1,k2,k3")) as c:
        assert (await c.get("/health")).json()["keys_configured"] == 3
        r = await c.post("/chat", json=chat_body("s-3", "hi"), headers={SIM: "key_1=429,key_2=500"})
        meta = r.json()["metadata"]
        assert meta["key_id"] == "key_3" and meta["fallback_attempts"] == 2
        provider.behaviors.update({"k1": 429, "k2": 500})
        r = await c.post("/chat", json=chat_body("s-4", "other"))
        meta = r.json()["metadata"]
        assert meta["key_id"] == "key_3" and meta["fallback_attempts"] == 2


async def test_failover_after_cached_response_via_other_key_still_labels_cache(client, provider):
    provider.behaviors["k1"] = 429
    await client.post("/chat", json=chat_body("s-1", "same"))
    r = (await client.post("/chat", json=chat_body("s-2", "same"))).json()
    assert r["metadata"]["resolution_source"] == "LLM_CACHE"
    assert r["metadata"]["key_id"] is None and r["metadata"]["fallback_attempts"] == 0


async def test_secrets_never_exposed(client, provider, caplog):
    caplog.set_level(logging.DEBUG)
    provider.behaviors["k1"] = 429
    r = await client.post("/chat", json=chat_body("s-sec", "hello"))
    h = await client.get("/health")
    m = await client.get("/sessions/s-sec/messages")
    for resp in (r, h, m):
        assert "k1" not in resp.text.replace("key_1", "") and '"k2"' not in resp.text
    assert "'k1'" not in caplog.text
