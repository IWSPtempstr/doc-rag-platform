"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { colors, radius, shadow, font, btnPrimary, inputBase, card } from "@/lib/styles";

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
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: font.xxl, fontWeight: 700, margin: 0 }}>RAG 问答</h1>
        <p style={{ fontSize: font.sm, color: colors.textSecondary, margin: "4px 0 0" }}>
          基于文档知识库的智能问答
        </p>
      </div>

      {/* Query Bar */}
      <div style={{
        ...card, display: "flex", gap: 10, alignItems: "center",
        padding: "14px 18px", marginBottom: 16,
      }}>
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleQuery()}
          placeholder="输入你的问题..."
          style={{ ...inputBase, flex: 1, fontSize: font.md }}
        />
        <button onClick={handleQuery} disabled={loading}
          style={{ ...btnPrimary, padding: "10px 24px", whiteSpace: "nowrap", opacity: loading ? 0.6 : 1 }}>
          {loading ? "查询中..." : "提问"}
        </button>
        <button onClick={loadSessions} style={{
          background: "transparent", color: colors.textSecondary, border: `1px solid ${colors.border}`,
          padding: "10px 16px", borderRadius: radius.sm, cursor: "pointer", fontSize: font.sm, fontWeight: 500,
          whiteSpace: "nowrap",
        }}>
          历史
        </button>
      </div>

      {error && (
        <div style={{
          padding: "12px 16px", background: "#fef2f2", color: colors.danger,
          borderRadius: radius.md, marginBottom: 16, fontSize: font.sm,
          border: "1px solid #fecaca",
        }}>{error}</div>
      )}

      {/* Answer */}
      {answer && (
        <div style={{ ...card, padding: 24 }}>
          <div style={{
            display: "flex", gap: 10, alignItems: "center", marginBottom: 16,
            paddingBottom: 12, borderBottom: `1px solid ${colors.borderLight}`,
          }}>
            <span style={{
              display: "inline-block", padding: "2px 10px", borderRadius: 12,
              fontSize: font.xs, fontWeight: 600, background: colors.primary, color: "#fff",
            }}>{answer.provider}</span>
            <span style={{ fontSize: font.xs, color: colors.textMuted }}>{answer.model}</span>
            {answer.cache_hit && (
              <span style={{
                fontSize: font.xs, color: colors.success, background: "#ecfdf5",
                padding: "2px 8px", borderRadius: radius.sm, fontWeight: 500,
              }}>缓存命中</span>
            )}
          </div>
          <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.8, fontSize: font.md, color: colors.text }}>
            {answer.answer}
          </div>

          {answer.citations?.length > 0 && (
            <details style={{ marginTop: 20 }}>
              <summary style={{
                cursor: "pointer", fontWeight: 600, fontSize: font.sm, color: colors.textSecondary,
                padding: "8px 0",
              }}>
                引用来源 ({answer.citations.length})
              </summary>
              <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 8 }}>
                {answer.citations.map((c: any, i: number) => (
                  <div key={i} style={{
                    padding: "12px 14px", background: colors.hover, borderRadius: radius.md,
                    borderLeft: `3px solid ${colors.primary}`, fontSize: font.sm,
                  }}>
                    <div style={{ color: colors.textSecondary, marginBottom: 6, fontSize: font.xs, display: "flex", gap: 12 }}>
                      <span style={{ fontWeight: 600, color: colors.text }}>{c.filename}</span>
                      <span>chunk: {c.chunk_id}</span>
                      <span>score: {c.score?.toFixed(3) || "N/A"}</span>
                    </div>
                    <div style={{ color: colors.text, lineHeight: 1.5 }}>
                      {c.content?.slice(0, 200)}{(c.content?.length || 0) > 200 ? "..." : ""}
                    </div>
                  </div>
                ))}
              </div>
            </details>
          )}
        </div>
      )}

      {/* Session History */}
      {showSessions && (
        <div style={{ ...card, marginTop: 24 }}>
          <h3 style={{ margin: "0 0 12px 0", fontSize: font.md, fontWeight: 600 }}>历史会话</h3>
          {sessions.length === 0 && (
            <div style={{ color: colors.textMuted, fontSize: font.sm, textAlign: "center", padding: 24 }}>暂无历史会话</div>
          )}
          {sessions.map((s: any) => (
            <div key={s.id} style={{
              padding: "10px 0", borderBottom: `1px solid ${colors.borderLight}`,
              fontSize: font.sm, display: "flex", justifyContent: "space-between", alignItems: "center",
            }}>
              <span style={{ fontWeight: 500, color: colors.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1, marginRight: 16 }}>
                {s.title?.slice(0, 80)}
              </span>
              <span style={{ color: colors.textMuted, fontSize: font.xs, whiteSpace: "nowrap" }}>
                {new Date(s.updated_at).toLocaleString()}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
