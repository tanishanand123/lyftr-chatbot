import { useState, useRef } from "react";
import { sendChatMessage, simulateFailureChat } from "./api";

function newSessionId() {
  return "s-" + Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
}

export default function App() {
  const [sessionId] = useState(newSessionId);
  const [systemPrompt, setSystemPrompt] = useState("");
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState([]);
  const [sending, setSending] = useState(false);
  const [simulateHeader, setSimulateHeader] = useState("");
  const listRef = useRef(null);

  async function handleSend() {
    const trimmed = input.trim();
    if (!trimmed || sending) return;

    setMessages((prev) => [...prev, { role: "user", content: trimmed }]);
    setInput("");
    setSending(true);

    try {
      const body = simulateHeader.trim()
        ? await simulateFailureChat(sessionId, trimmed, simulateHeader.trim())
        : await sendChatMessage(sessionId, trimmed, systemPrompt.trim());
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: body.reply, metadata: body.metadata },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "error",
          content: err.message || "Something went wrong. Please try again.",
        },
      ]);
    } finally {
      setSending(false);
    }
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <div style={styles.page}>
      <div style={styles.container}>
        <h1 style={styles.title}>Lyftr AI Chatbot</h1>
        <div style={styles.sessionRow}>
          <span style={styles.sessionLabel}>Session: {sessionId}</span>
        </div>

        <div style={styles.systemPromptRow}>
          <label htmlFor="system-prompt" style={styles.label}>
            System prompt (optional)
          </label>
          <input
            id="system-prompt"
            data-testid="system-prompt-input"
            type="text"
            value={systemPrompt}
            onChange={(e) => setSystemPrompt(e.target.value)}
            placeholder="e.g. You are a concise assistant."
            style={styles.input}
          />
        </div>

        <div style={styles.systemPromptRow}>
          <label htmlFor="simulate-failure" style={styles.label}>
            X-Simulate-Failure header (optional, for demo)
          </label>
          <input
            id="simulate-failure"
            type="text"
            value={simulateHeader}
            onChange={(e) => setSimulateHeader(e.target.value)}
            placeholder="e.g. key_1=429"
            style={styles.input}
          />
        </div>

        <div style={styles.chatBox} ref={listRef}>
          {messages.length === 0 && (
            <div style={styles.emptyState}>Send a message to start the conversation.</div>
          )}
          {messages.map((m, i) => {
            if (m.role === "user") {
              return (
                <div key={i} style={styles.userBubbleRow}>
                  <div style={styles.userBubble}>{m.content}</div>
                </div>
              );
            }
            if (m.role === "error") {
              return (
                <div key={i} style={styles.errorBubble}>
                  {m.content}
                </div>
              );
            }
            return (
              <div key={i} style={styles.assistantBubbleRow} data-testid="assistant-message">
                <div style={styles.assistantBubble}>
                  <div>{m.content}</div>
                  {m.metadata && (
                    <div style={styles.metaRow}>
                      <span data-testid="meta-source" style={styles.metaTag}>
                        {m.metadata.resolution_source}
                      </span>
                      <span data-testid="meta-model" style={styles.metaTag}>
                        {m.metadata.model}
                      </span>
                      <span data-testid="meta-latency" style={styles.metaTag}>
                        {m.metadata.latency_ms} ms
                      </span>
                      <span data-testid="meta-input-tokens" style={styles.metaTag}>
                        in: {m.metadata.input_tokens}
                      </span>
                      <span data-testid="meta-output-tokens" style={styles.metaTag}>
                        out: {m.metadata.output_tokens}
                      </span>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        <div style={styles.inputRow}>
          <textarea
            data-testid="chat-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type a message..."
            style={styles.textarea}
            rows={2}
          />
          <button
            data-testid="send-button"
            onClick={handleSend}
            disabled={sending || !input.trim()}
            style={styles.sendButton}
          >
            {sending ? "Sending..." : "Send"}
          </button>
        </div>
      </div>
    </div>
  );
}

const styles = {
  page: {
    minHeight: "100vh",
    background: "#0f172a",
    display: "flex",
    justifyContent: "center",
    padding: "24px",
    fontFamily: "system-ui, sans-serif",
  },
  container: {
    width: "100%",
    maxWidth: "720px",
    display: "flex",
    flexDirection: "column",
    gap: "12px",
  },
  title: { color: "#f8fafc", margin: 0 },
  sessionRow: { color: "#94a3b8", fontSize: "12px" },
  sessionLabel: {},
  systemPromptRow: { display: "flex", flexDirection: "column", gap: "4px" },
  label: { color: "#cbd5e1", fontSize: "12px" },
  input: {
    padding: "8px 10px",
    borderRadius: "6px",
    border: "1px solid #334155",
    background: "#1e293b",
    color: "#f1f5f9",
  },
  chatBox: {
    background: "#1e293b",
    borderRadius: "10px",
    padding: "16px",
    minHeight: "360px",
    maxHeight: "480px",
    overflowY: "auto",
    display: "flex",
    flexDirection: "column",
    gap: "10px",
  },
  emptyState: { color: "#64748b", textAlign: "center", marginTop: "140px" },
  userBubbleRow: { display: "flex", justifyContent: "flex-end" },
  userBubble: {
    background: "#2563eb",
    color: "white",
    padding: "8px 12px",
    borderRadius: "10px",
    maxWidth: "80%",
  },
  assistantBubbleRow: { display: "flex", justifyContent: "flex-start" },
  assistantBubble: {
    background: "#334155",
    color: "#f1f5f9",
    padding: "8px 12px",
    borderRadius: "10px",
    maxWidth: "85%",
  },
  errorBubble: {
    background: "#7f1d1d",
    color: "#fecaca",
    padding: "8px 12px",
    borderRadius: "10px",
    alignSelf: "center",
  },
  metaRow: { display: "flex", flexWrap: "wrap", gap: "6px", marginTop: "8px" },
  metaTag: {
    fontSize: "11px",
    background: "#0f172a",
    color: "#93c5fd",
    padding: "2px 6px",
    borderRadius: "4px",
  },
  inputRow: { display: "flex", gap: "8px" },
  textarea: {
    flex: 1,
    padding: "10px",
    borderRadius: "8px",
    border: "1px solid #334155",
    background: "#1e293b",
    color: "#f1f5f9",
    resize: "none",
  },
  sendButton: {
    padding: "0 20px",
    borderRadius: "8px",
    border: "none",
    background: "#2563eb",
    color: "white",
    cursor: "pointer",
  },
};
