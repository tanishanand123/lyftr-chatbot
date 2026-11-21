import os
import sys
import uuid

os.environ["DATABASE_URL"] = "sqlite:///./data/test.db"
os.environ["LLM_API_KEYS"] = "testkey1,testkey2"
os.environ["ENABLE_FAILURE_SIMULATION"] = "true"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402
from app.llm import key_pool  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)


def setup_function():
    db.init_db()
    key_pool._cache.clear()


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["keys_configured"] == 2
    assert body["cache_enabled"] is True


def test_chat_validation_empty_message():
    resp = client.post("/chat", json={"session_id": "s1", "message": "   "})
    assert resp.status_code == 422
    assert "detail" in resp.json()


def test_chat_validation_long_message():
    resp = client.post("/chat", json={"session_id": "s1", "message": "a" * 4001})
    assert resp.status_code == 422


def test_unknown_session_history_404():
    resp = client.get(f"/sessions/{uuid.uuid4()}/messages")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "session not found"


def test_all_providers_unavailable_503():
    session_id = f"s-{uuid.uuid4()}"
    resp = client.post(
        "/chat",
        json={"session_id": session_id, "message": "hello there"},
        headers={"X-Simulate-Failure": "*=429"},
    )
    assert resp.status_code == 503
    assert resp.json()["detail"] == "all providers unavailable"
    # failed request must not be added to history
    hist = client.get(f"/sessions/{session_id}/messages")
    assert hist.status_code == 404


def test_failover_to_key_2(monkeypatch):
    import app.llm as llm_module

    calls = []

    def fake_completion(model, api_key, messages, caching=False):
        calls.append(api_key)
        if api_key == "testkey1":
            raise Exception("simulated provider 500 error")

        class Usage:
            prompt_tokens = 10
            completion_tokens = 5

        class Message:
            content = "fake reply"

        class Choice:
            message = Message()

        class Response:
            choices = [Choice()]
            usage = Usage()

        return Response()

    monkeypatch.setattr(llm_module.litellm, "completion", fake_completion)

    session_id = f"s-{uuid.uuid4()}"
    resp = client.post(
        "/chat",
        json={"session_id": session_id, "message": "trigger failover please"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["metadata"]["key_id"] == "key_2"
    assert body["metadata"]["fallback_attempts"] == 1
    assert body["metadata"]["resolution_source"] == "LIVE_INFERENCE"


def test_cache_hit_on_repeat_message(monkeypatch):
    import app.llm as llm_module

    call_count = {"n": 0}

    def fake_completion(model, api_key, messages, caching=False):
        call_count["n"] += 1

        class Usage:
            prompt_tokens = 20
            completion_tokens = 8

        class Message:
            content = "cached-capable reply"

        class Choice:
            message = Message()

        class Response:
            choices = [Choice()]
            usage = Usage()

        return Response()

    monkeypatch.setattr(llm_module.litellm, "completion", fake_completion)

    session_a = f"s-{uuid.uuid4()}"
    session_b = f"s-{uuid.uuid4()}"

    r1 = client.post("/chat", json={"session_id": session_a, "message": "What is the capital of France?"})
    r2 = client.post("/chat", json={"session_id": session_b, "message": "What is the capital of France?"})

    assert r1.json()["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    assert r2.json()["metadata"]["resolution_source"] == "LLM_CACHE"
    assert r2.json()["reply"] == r1.json()["reply"]
    assert r2.json()["metadata"]["key_id"] is None
    assert r2.json()["metadata"]["fallback_attempts"] == 0
    assert call_count["n"] == 1
