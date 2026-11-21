const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export async function sendChatMessage(sessionId, message, systemPrompt) {
  const res = await fetch(`${BASE_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      message,
      ...(systemPrompt ? { system_prompt: systemPrompt } : {}),
    }),
  });

  let body;
  try {
    body = await res.json();
  } catch {
    body = { detail: "Unexpected server response" };
  }

  if (!res.ok) {
    const err = new Error(body.detail || "Request failed");
    err.status = res.status;
    throw err;
  }

  return body;
}

export async function simulateFailureChat(sessionId, message, simulateHeader) {
  const res = await fetch(`${BASE_URL}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Simulate-Failure": simulateHeader,
    },
    body: JSON.stringify({ session_id: sessionId, message }),
  });
  const body = await res.json();
  if (!res.ok) {
    const err = new Error(body.detail || "Request failed");
    err.status = res.status;
    throw err;
  }
  return body;
}
