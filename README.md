# Lyftr AI — LLM Chatbot with Key Failover and Response Caching

## 1. Live URLs

- Frontend: `<fill in after deploying, e.g. Vercel/Netlify URL>`
- Backend: `<fill in after deploying, e.g. Render/Railway URL>`

## 2. Run locally

### With Docker (recommended)

```bash
cp .env.example .env   # fill in at least 2 real LLM_API_KEYS
make up                 # builds and starts backend (:8000) and frontend (:3000)
make down                # stop everything
```

### Without Docker

Backend:
```bash
cd backend
python -m venv .venv
.venv/Scripts/activate       # Windows; use `source .venv/bin/activate` on macOS/Linux
pip install -r requirements.txt
export LLM_API_KEYS="key1,key2"
export DATABASE_URL="sqlite:///./data/app.db"
export ALLOWED_ORIGINS="http://localhost:3000"
export ENABLE_FAILURE_SIMULATION=true
uvicorn app.main:app --reload --port 8000
```

Frontend:
```bash
cd frontend
npm install
VITE_API_BASE_URL=http://localhost:8000 npm run dev
```

### Tests

```bash
cd backend
.venv/Scripts/python -m pytest tests/ -q
```

## 3. Design decisions

**Key fallback.** `app/llm.py` implements a `KeyPool` that iterates the configured
keys (`key_1`, `key_2`, ...) in order. For each key it calls `litellm.completion()`
with that key's credentials. If the call raises (or the `X-Simulate-Failure` header
forces a status for that key), and the resulting status is one of `429/500/502/503`,
the pool increments `fallback_attempts` and moves to the next key. Only once every
key has failed does the endpoint return `503 {"detail": "all providers unavailable"}`.
This is deliberately a thin wrapper directly around LiteLLM's `completion()` call
(rather than LiteLLM's router object) so that the per-key simulated-failure hook
required by the assignment could be implemented precisely and deterministically.

**Caching.** The cache key is `sha256(model + full_message_list)`, matching the
assignment's requirement that the key include the system prompt, full history, and
new message. LiteLLM's cache (`litellm.Cache(type="local")`) is configured and
enabled on `/health`, and backs the actual provider call path; an explicit
application-level cache map stores the `{reply, model, input_tokens, output_tokens}`
tuple for the exact-match lookup so that resolution source, identical reply text,
null `key_id`, and `fallback_attempts=0` are guaranteed on a hit, independent of any
internal LiteLLM cache-object implementation details. A cache hit short-circuits
before any key is touched, so it is always faster than a live call and is not
affected by `X-Simulate-Failure`.

**SQLite session storage.** `messages` table stores one row per user/assistant
turn, keyed by `session_id`, with assistant rows carrying a JSON `metadata` blob
(resolution source, model, tokens, etc.). History sent to the LLM is reconstructed
per-session from this table, prefixed with the (per-session or default) system
prompt. The DB file lives at the path given by `DATABASE_URL`, mounted as a Docker
named volume so history survives container restarts. Failed requests (422/503) are
never written to history.

## 4. Verification

**Health:**
```bash
curl http://localhost:8000/health
```

**Cache hit (send the same first message to two different sessions):**
```bash
curl -s -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
  -d '{"session_id":"s-cache-1","message":"What is the capital of France?"}'
curl -s -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
  -d '{"session_id":"s-cache-2","message":"What is the capital of France?"}'
# second call returns resolution_source = LLM_CACHE, identical reply, lower latency_ms
```

**Failover (requires ENABLE_FAILURE_SIMULATION=true on the backend):**
```bash
curl -s -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
  -H "X-Simulate-Failure: key_1=429" \
  -d '{"session_id":"s-failover","message":"hello"}'
# 200, metadata.key_id = key_2, metadata.fallback_attempts = 1

curl -s -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
  -H "X-Simulate-Failure: *=429" \
  -d '{"session_id":"s-failover-2","message":"hello"}'
# 503 {"detail": "all providers unavailable"}
```

**Token usage:** every `/chat` response includes `input_tokens`/`output_tokens` for
that request only; shown in the UI under each assistant bubble via
`meta-input-tokens` / `meta-output-tokens`.

**Multi-turn / history:**
```bash
curl http://localhost:8000/sessions/s-cache-1/messages
```

## 5. Setup Used

- Editor: VS Code (Claude Code extension)
- AI tools: Claude (Sonnet) via Claude Code, used to scaffold and implement the
  backend, frontend, Docker setup, and tests in this repository.

## 6. Bonus features (if any)

- Optional per-session `system_prompt` field, persisted per session and reused on
  subsequent turns if not resent.
- Backend test suite (`backend/tests/test_api.py`) covering validation errors,
  404 on unknown session, 503 on total provider failure, failover to a second key,
  and a cache-hit scenario with monkeypatched LLM calls (no network/API keys
  required to run tests).
- Readable in-chat error messages on 422/503 in the frontend instead of a blank
  screen.
