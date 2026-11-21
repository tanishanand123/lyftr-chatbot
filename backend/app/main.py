from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from . import db
from .config import settings
from .llm import AllProvidersUnavailable, key_pool, parse_simulate_header


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="Lyftr Chatbot Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=128)
    message: str
    system_prompt: str | None = None

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        trimmed = v.strip()
        if not (1 <= len(trimmed) <= 4000):
            raise ValueError("message must be 1-4000 chars after trimming whitespace")
        return trimmed


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=503, content={"detail": "all providers unavailable"})


@app.get("/health")
def health():
    return {
        "status": "ok",
        "keys_configured": key_pool.configured_count,
        "cache_enabled": True,
    }


@app.post("/chat")
def chat(req: ChatRequest, request: Request):
    simulate_header = request.headers.get("X-Simulate-Failure")
    simulate = {}
    if settings.enable_failure_simulation:
        simulate = parse_simulate_header(simulate_header)

    system_prompt = req.system_prompt or db.get_system_prompt(req.session_id) or settings.default_system_prompt
    if req.system_prompt:
        db.set_system_prompt(req.session_id, req.system_prompt)

    history = db.get_history_for_llm(req.session_id)
    messages = [{"role": "system", "content": system_prompt}] + history + [
        {"role": "user", "content": req.message}
    ]

    try:
        result = key_pool.chat(messages, simulate=simulate)
    except AllProvidersUnavailable:
        raise HTTPException(status_code=503, detail="all providers unavailable")

    db.add_message(req.session_id, "user", req.message)
    db.add_message(
        req.session_id,
        "assistant",
        result.reply,
        metadata={
            "resolution_source": result.resolution_source,
            "model": result.model,
            "latency_ms": result.latency_ms,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "key_id": result.key_id,
            "fallback_attempts": result.fallback_attempts,
        },
    )

    return {
        "session_id": req.session_id,
        "reply": result.reply,
        "metadata": {
            "resolution_source": result.resolution_source,
            "model": result.model,
            "latency_ms": result.latency_ms,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "key_id": result.key_id,
            "fallback_attempts": result.fallback_attempts,
        },
    }


@app.get("/sessions/{session_id}/messages")
def get_session_messages(session_id: str):
    if not db.session_exists(session_id):
        raise HTTPException(status_code=404, detail="session not found")
    return {"session_id": session_id, "messages": db.get_messages(session_id)}
