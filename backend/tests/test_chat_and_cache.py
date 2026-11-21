from tests.conftest import chat_body

META_KEYS = {
    "resolution_source", "model", "latency_ms", "input_tokens", "output_tokens",
    "key_id", "fallback_attempts",
}


async def test_live_inference_contract(client, provider):
    r = await client.post("/chat", json=chat_body("s-1", "What is 2+2?"))
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == "s-1" and body["reply"]
    meta = body["metadata"]
    assert set(meta) >= META_KEYS
    assert meta["resolution_source"] == "LIVE_INFERENCE"
    assert meta["key_id"] == "key_1" and meta["fallback_attempts"] == 0
    assert meta["model"] == "fake/test-model"  # LiteLLM model name, provider prefix kept
    assert isinstance(meta["latency_ms"], int) and meta["latency_ms"] >= 1
    assert isinstance(meta["input_tokens"], int) and meta["input_tokens"] > 0
    assert isinstance(meta["output_tokens"], int) and meta["output_tokens"] > 0
    assert provider.calls_for("k1") == 1


async def test_cross_session_cache_hit(client, provider):
    a = (await client.post("/chat", json=chat_body("s-1", "What is 2+2?"))).json()
    b = (await client.post("/chat", json=chat_body("s-2", "What is 2+2?"))).json()
    assert b["metadata"]["resolution_source"] == "LLM_CACHE"
    assert b["reply"] == a["reply"]
    assert b["metadata"]["key_id"] is None
    assert b["metadata"]["fallback_attempts"] == 0
    assert b["metadata"]["input_tokens"] == a["metadata"]["input_tokens"]
    assert b["metadata"]["output_tokens"] == a["metadata"]["output_tokens"]
    assert b["metadata"]["model"] == a["metadata"]["model"]
    assert len(provider.calls) == 1  # provider invoked exactly once


async def test_cache_hit_is_not_slower_than_live(client, provider):
    a = (await client.post("/chat", json=chat_body("s-1", "Explain caching"))).json()
    b = (await client.post("/chat", json=chat_body("s-2", "Explain caching"))).json()
    assert b["metadata"]["latency_ms"] <= a["metadata"]["latency_ms"]


async def test_different_prompt_never_hits_cache(client, provider):
    await client.post("/chat", json=chat_body("s-1", "What is 2+2?"))
    r = (await client.post("/chat", json=chat_body("s-3", "What is 3+3?"))).json()
    assert r["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    assert r["metadata"]["key_id"] == "key_1"
    assert "3+3" in r["reply"]
    assert len(provider.calls) == 2


async def test_cache_disabled_always_live(tmp_settings, provider):
    from tests.conftest import running_app

    async with running_app(tmp_settings(cache_enabled=False)) as c:
        await c.post("/chat", json=chat_body("s-1", "hello"))
        r = (await c.post("/chat", json=chat_body("s-2", "hello"))).json()
        assert r["metadata"]["resolution_source"] == "LIVE_INFERENCE"
        assert len(provider.calls) == 2


async def test_tokens_are_per_request_not_cumulative(client):
    t1 = (await client.post("/chat", json=chat_body("s-a", "Tell me about cats"))).json()
    t2 = (await client.post("/chat", json=chat_body("s-a", "And dogs?"))).json()
    first_other = (await client.post("/chat", json=chat_body("s-b", "Tell me about dogs"))).json()
    # Equal-length first messages in two new sessions report ~equal input tokens.
    assert abs(t1["metadata"]["input_tokens"] - first_other["metadata"]["input_tokens"]) <= 1
    # The second turn carries history, so its prompt is larger, but output stays per-request.
    assert t2["metadata"]["input_tokens"] > t1["metadata"]["input_tokens"]
    assert t2["metadata"]["output_tokens"] < t2["metadata"]["input_tokens"] + 50


async def test_multi_turn_context_sent_to_llm(client, provider):
    await client.post("/chat", json=chat_body("s-mt", "My name is Alex."))
    r = (await client.post("/chat", json=chat_body("s-mt", "What is my name?"))).json()
    sent = provider.calls[-1][1]
    assert [m["role"] for m in sent] == ["system", "user", "assistant", "user"]
    assert sent[1]["content"] == "My name is Alex."
    assert sent[3]["content"] == "What is my name?"
    assert "Alex" in r["reply"]


async def test_system_prompt_override_is_used_and_persisted_for_session(client, provider):
    await client.post("/chat", json=chat_body("s-sp", "hi", system_prompt="  Talk like a pirate.  "))
    assert provider.calls[-1][1][0] == {"role": "system", "content": "Talk like a pirate."}
    await client.post("/chat", json=chat_body("s-sp", "again"))
    assert provider.calls[-1][1][0]["content"] == "Talk like a pirate."
    await client.post("/chat", json=chat_body("s-default", "hi"))
    assert provider.calls[-1][1][0]["content"] == "You are a helpful, concise AI assistant."


async def test_message_is_trimmed_before_use(client, provider):
    await client.post("/chat", json=chat_body("s-trim", "   padded   "))
    assert provider.calls[-1][1][-1]["content"] == "padded"


async def test_empty_reply_fails_over_to_next_key(client, provider):
    provider.behaviors["k1"] = "empty"
    r = (await client.post("/chat", json=chat_body("s-e", "hello"))).json()
    assert r["metadata"]["key_id"] == "key_2"
    assert r["metadata"]["fallback_attempts"] == 1
    assert r["reply"]
