"use client";

import { useState } from "react";
import { api } from "@/lib/api";

export default function ChatPage() {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [sessions, setSessions] = useState<any[]>([]);
  const [showSessions, setShowSessions] = useState(false);

  const handleQuery = async () => {
    if (!question.trim()) return;
    setLoading(true);
    setError("");
    setAnswer(null);
    try {
      const result: any = await api.query(question);
      setAnswer(result);
    } catch (err: any) {
      setError(err.message);
    }
    setLoading(false);
  };

  const loadSessions = async () => {
    const s: any = await api.listSessions();
    setSessions(s);
    setShowSessions(true);
  };

  return (
    <div>
      <h1>RAG 问答</h1>
      <div style={{ display: "flex", gap: 12, marginBottom: 16 }}>
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleQuery()}
          placeholder="输入你的问题..."
          style={{ flex: 1, padding: "10px 14px", borderRadius: 6, border: "1px solid #ccc", fontSize: 15 }}
        />
        <button onClick={handleQuery} disabled={loading} style={{ padding: "10px 24px", background: "#1a1a2e", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer", fontWeight: 600 }}>
          {loading ? "查询中..." : "提问"}
        </button>
        <button onClick={loadSessions} style={{ padding: "10px 16px", background: "#eee", border: "1px solid #ccc", borderRadius: 6, cursor: "pointer" }}>
          历史
        </button>
      </div>

      {error && <div style={{ padding: 12, background: "#ffebee", color: "#c62828", borderRadius: 6, marginBottom: 12, fontSize: 14 }}>{error}</div>}

      {answer && (
        <div style={{ background: "#fff", borderRadius: 8, padding: 20, boxShadow: "0 1px 3px rgba(0,0,0,0.1)" }}>
          <div style={{ marginBottom: 12, fontSize: 11, color: "#999" }}>
            {answer.provider} / {answer.model} {answer.cache_hit ? "(缓存命中)" : ""}
          </div>
          <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.7, fontSize: 15 }}>{answer.answer}</div>

          {answer.citations?.length > 0 && (
            <details style={{ marginTop: 16 }}>
              <summary style={{ cursor: "pointer", fontWeight: 600, fontSize: 13, color: "#555" }}>引用来源 ({answer.citations.length})</summary>
              {answer.citations.map((c: any, i: number) => (
                <div key={i} style={{ marginTop: 8, padding: 10, background: "#f9f9f9", borderRadius: 4, borderLeft: "3px solid #1a1a2e", fontSize: 13 }}>
                  <div style={{ color: "#888", marginBottom: 4 }}>
                    {c.filename} — chunk: {c.chunk_id} (score: {c.score?.toFixed(3) || "N/A"})
                  </div>
                  <div>{c.content?.slice(0, 200)}{(c.content?.length || 0) > 200 ? "..." : ""}</div>
                </div>
              ))}
            </details>
          )}
        </div>
      )}

      {showSessions && (
        <div style={{ marginTop: 24, background: "#fff", borderRadius: 8, padding: 16, boxShadow: "0 1px 3px rgba(0,0,0,0.1)" }}>
          <h3 style={{ marginTop: 0 }}>历史会话</h3>
          {sessions.map((s: any) => (
            <div key={s.id} style={{ padding: "8px 0", borderBottom: "1px solid #eee", fontSize: 14 }}>
              <strong>{s.title?.slice(0, 80)}</strong>
              <span style={{ color: "#999", marginLeft: 12 }}>{new Date(s.updated_at).toLocaleString()}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
