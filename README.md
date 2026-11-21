# Lyftr AI — LLM Chatbot with Key Failover and Response Caching

React 18 + TypeScript + Vite frontend, Python 3.12 + FastAPI backend, LiteLLM `Router` + built-in `Cache`, SQLite storage, Docker Compose.

## 1. Live URLs

- Frontend: _add the deployed frontend URL here after deploying_
- Backend: _add the deployed backend URL here after deploying_ (`/health` should return `keys_configured >= 2`)
- Repository: _add the public GitHub URL here_

## 2. Run locally: with Docker and without

### With Docker (recommended)

```bash
cp .env.example .env      # then put >= 2 real keys in LLM_API_KEYS (comma-separated)
make up                   # backend http://localhost:8000, frontend http://localhost:3000
make down                 # stops containers; the sqlite_data volume is kept
```

`make clean` also deletes the volume (history is lost). `make up` creates `.env` from `.env.example` if it is missing.

### Without Docker

Backend (Python 3.12):

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
export LLM_API_KEYS="key-one,key-two" DATABASE_URL="sqlite:///./data/app.db" \
       ALLOWED_ORIGINS="http://localhost:3000" ENABLE_FAILURE_SIMULATION=true
uvicorn app.main:app --port 8000 --workers 1
python -m pytest -q       # backend tests (no API calls, no cost)
```

Frontend (Node 20+):

```bash
cd frontend
npm ci
VITE_API_BASE_URL=http://localhost:8000 npm run dev   # http://localhost:3000
npm run build             # type-check + production build
```

Environment variables are listed in `.env.example`. Required: `LLM_API_KEYS`, `DATABASE_URL`, `ALLOWED_ORIGINS`, `ENABLE_FAILURE_SIMULATION`. Optional: `LLM_MODEL`, `LLM_MODELS`, `DEFAULT_SYSTEM_PROMPT`, `CACHE_ENABLED`, `CACHE_TYPE`, `CACHE_TTL_SECONDS`, `CACHE_DISK_DIR`, `LLM_TIMEOUT_SECONDS`, `VITE_API_BASE_URL` (frontend build time).

## 3. Design decisions: key fallback, caching, SQLite session storage

**Key fallback.** `LLM_API_KEYS` becomes a `litellm.Router` pool with logical deployments `key_1 … key_N` (one per key, optionally a different model each through `LLM_MODELS`). Requests start at `key_1`; the Router's `fallbacks` chain moves on to the next key on 429, quota and 5xx errors with `num_retries=0` and cooldowns disabled, so failover is immediate and a failed key is tried again on the next request. Raw keys stay inside the Router; only ids (`key_1`) are exposed, and a log filter redacts key values. If every key fails the API returns `503 {"detail": "all providers unavailable"}`. An empty provider reply is treated as a failure and the remaining keys are tried.

**Failure simulation.** With `ENABLE_FAILURE_SIMULATION=true`, `X-Simulate-Failure: key_1=429,key_2=500` / `*=429` is parsed per request (statuses 429/500/502/503). Simulation walks the keys in order, raises the matching LiteLLM exception for simulated keys and calls the healthy ones through the Router with the cache disabled for that call (`no-cache` + `no-store`), so failover always runs and simulated results never enter the cache. Nothing global changes, so the next request without the header uses `key_1` normally. With the flag off the header is ignored.

**Caching.** LiteLLM's built-in cache (`CACHE_TYPE=local` in-memory by default, or `disk`) keys on model + the full message list, independent of `session_id`. The same first prompt in a new session is therefore a hit: `LLM_CACHE`, identical reply, stored token usage, `key_id: null`, `fallback_attempts: 0`. Uvicorn runs with one worker so the in-memory cache is shared by all requests. Known edge: a reply first produced by `key_2` after a failover is cached under `key_2`'s group, so a later `key_1`-first request still gets a correct cache hit but does one extra attempt on `key_1` first.

**SQLite sessions.** `messages` (exact schema from the assignment) plus a `sessions` table that stores the per-session system prompt. The schema is created at startup in the file from `DATABASE_URL` (`sqlite:////data/app.db` → the `sqlite_data` named volume). WAL mode and `aiosqlite` keep database I/O off the event loop. The user and assistant rows are written in one transaction only after a successful LLM reply, so 422 and 503 responses leave no rows. The client sends only the new message; the backend rebuilds `[system, …history, user]`. The system prompt resolves as request `system_prompt` → stored session prompt → `DEFAULT_SYSTEM_PROMPT`.

**Errors.** Every error is JSON with `detail` (422 validation, 404 `session not found`, 503, generic 500); no stack traces or HTML.

## 4. Verification: how to see failover, cache hits and per-message token usage

```bash
B=http://localhost:8000   # or your deployed backend
curl $B/health

# Live inference, then a cache hit from a NEW session (LLM_CACHE, key_id null, lower latency)
curl -s $B/chat -H 'Content-Type: application/json' -d '{"session_id":"s-a","message":"What is the capital of France?"}'
curl -s $B/chat -H 'Content-Type: application/json' -d '{"session_id":"s-b","message":"What is the capital of France?"}'

# Failover (answered by key_2, fallback_attempts 1) — even for the cached prompt
curl -s $B/chat -H 'Content-Type: application/json' -H 'X-Simulate-Failure: key_1=429' \
     -d '{"session_id":"s-c","message":"What is the capital of France?"}'

# All keys fail -> 503 {"detail":"all providers unavailable"}, nothing stored
curl -si $B/chat -H 'Content-Type: application/json' -H 'X-Simulate-Failure: *=429' \
     -d '{"session_id":"s-d","message":"hello"}'

curl -s $B/sessions/s-a/messages     # stored history with per-message metadata
curl -si $B/sessions/nope/messages   # 404 {"detail":"session not found"}
```

In the UI each assistant reply shows source, model, latency and that request's input/output tokens (never a running total), plus key id and fallback count. The header has a **New Session** button and a failure-simulation dropdown (default Off); reloading the page also starts a new session, so sending the same prompt after a reload demonstrates a cache hit. History persistence: send a message, run `make down && make up`, then `GET /sessions/<id>/messages`.

## 5. Setup Used: your editor and AI tools

AI tools: Claude (implementation, tests) working from the assignment PDF and a Gemini-generated architecture blueprint. Add your own editor here.

## 6. Bonus features (if any)

- Failure-simulation dropdown and per-reply `key_id` / `fallback_attempts` indicators in the UI (outside the required test ids).
- Optional system-prompt field (`system-prompt-input`) that exercises `system_prompt` end to end.
- "New Session" button for one-click cross-session cache demos.
- Optional disk cache (`CACHE_TYPE=disk`), per-key model lists (`LLM_MODELS`), secret-redacting log filter, per-session request lock.
- Backend test suite (pytest) that runs real LiteLLM Router/Cache logic against a fake provider: no network, no cost.
