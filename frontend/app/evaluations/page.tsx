"use client";

import { useState } from "react";
import { api } from "@/lib/api";

export default function EvaluationsPage() {
  const [strategy, setStrategy] = useState("dense");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [history, setHistory] = useState<any[]>([]);

  const run = async () => {
    setRunning(true);
    setResult(null);
    try {
      const r: any = await api.runEvaluation(strategy);
      setResult(r);
      loadHistory();
    } catch (err: any) {
      setResult({ error: err.message });
    }
    setRunning(false);
  };

  const loadHistory = async () => {
    const h: any = await api.getEvaluationResults();
    setHistory(h);
  };

  return (
    <div>
      <h1>评估 (v1.1)</h1>
      <div style={{ marginBottom: 16, display: "flex", gap: 12, alignItems: "center" }}>
        <select value={strategy} onChange={(e) => setStrategy(e.target.value)} style={{ padding: "8px 12px", borderRadius: 4, border: "1px solid #ccc" }}>
          <option value="dense">Dense</option>
          <option value="hybrid">Hybrid (Dense + BM25 + RRF)</option>
          <option value="hybrid_rerank">Hybrid + Rerank</option>
        </select>
        <button onClick={run} disabled={running} style={{ padding: "8px 20px", background: "#1a1a2e", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer" }}>
          {running ? "运行中..." : "运行评估"}
        </button>
        <button onClick={loadHistory} style={{ padding: "8px 16px", cursor: "pointer", borderRadius: 4, border: "1px solid #ccc" }}>加载历史</button>
      </div>

      {result && (
        <div style={{ background: "#fff", borderRadius: 8, padding: 20, marginBottom: 20, boxShadow: "0 1px 3px rgba(0,0,0,0.1)" }}>
          {result.error ? (
            <div style={{ color: "#f44336" }}>错误: {result.error}</div>
          ) : (
            <>
              <div style={{ display: "flex", gap: 24, marginBottom: 16 }}>
                <Metric label="策略" value={result.strategy} />
                <Metric label="Hit Rate" value={`${((result.hit_rate || 0) * 100).toFixed(1)}%`} />
                <Metric label="问题数" value={String(result.total || 0)} />
              </div>
              {(result.results || []).map((r: any, i: number) => (
                <div key={i} style={{ padding: "8px 0", borderBottom: "1px solid #eee", fontSize: 13 }}>
                  <span style={{ color: r.hit ? "#4caf50" : "#f44336", fontWeight: 700, marginRight: 8 }}>
                    {r.hit ? "HIT" : "MISS"}
                  </span>
                  Q{i + 1}: {r.question}
                  <span style={{ color: "#999", marginLeft: 8 }}>({r.duration_s}s)</span>
                </div>
              ))}
            </>
          )}
        </div>
      )}

      {history.length > 0 && (
        <div style={{ background: "#fff", borderRadius: 8, padding: 16, boxShadow: "0 1px 3px rgba(0,0,0,0.1)" }}>
          <h3 style={{ marginTop: 0 }}>历史评估</h3>
          {history.map((h: any) => (
            <div key={h.id} style={{ padding: "6px 0", fontSize: 13, borderBottom: "1px solid #eee" }}>
              #{h.id} strategy={h.strategy} hit_rate={(h.hit_rate * 100).toFixed(1)}% — {new Date(h.created_at).toLocaleString()}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const Metric = ({ label, value }: { label: string; value: string }) => (
  <div>
    <div style={{ fontSize: 11, color: "#999" }}>{label}</div>
    <div style={{ fontSize: 18, fontWeight: 700 }}>{value}</div>
  </div>
);
