"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { ProtectedRoute } from "@/lib/auth";
import type { FinanceEvalResult } from "@/lib/types";
import { colors, font, card, btnPrimary, inputBase } from "@/lib/styles";

export default function FinanceEvaluationsPage() {
  return <ProtectedRoute><FinanceEvaluationsPageInner /></ProtectedRoute>;
}

function FinanceEvaluationsPageInner() {
  const [dataset, setDataset] = useState("custom_10k");
  const [running, setRunning] = useState(false);
  const [results, setResults] = useState<FinanceEvalResult[]>([]);
  const [message, setMessage] = useState("");

  const load = () => api.listFinanceEvaluationResults().then((rows: any) => setResults(rows)).catch(() => setResults([]));
  useEffect(() => { load(); }, []);

  const run = async () => {
    setRunning(true);
    setMessage("");
    try {
      await api.runFinanceEvaluation({ dataset_source: dataset, strategy: "finance_agent" });
      setMessage("评估完成");
      load();
    } catch (err: any) {
      setMessage(`评估失败: ${err.message}`);
    } finally {
      setRunning(false);
    }
  };

  return (
    <div>
      <h1 style={{ margin: "0 0 6px", fontSize: font.xxl }}>金融评估</h1>
      <p style={{ margin: "0 0 20px", color: colors.textSecondary, fontSize: font.sm }}>
        使用 FinQA/TAT-QA 风格种子集和自建 10-K 任务评估 RAG + Agent。
      </p>

      <div style={card}>
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <select value={dataset} onChange={(e) => setDataset(e.target.value)} style={{ ...inputBase, minWidth: 180 }}>
            <option value="custom_10k">Custom 10-K</option>
            <option value="finqa">FinQA-style</option>
            <option value="tatqa">TAT-QA-style</option>
          </select>
          <button onClick={run} disabled={running} style={{ ...btnPrimary, opacity: running ? 0.6 : 1 }}>
            {running ? "运行中..." : "运行评估"}
          </button>
          {message && <span style={{ color: message.includes("失败") ? colors.danger : colors.success, fontSize: font.sm }}>{message}</span>}
        </div>
      </div>

      <div style={card}>
        <h2 style={{ margin: "0 0 12px", fontSize: font.lg }}>历史结果</h2>
        {results.length === 0 ? (
          <div style={{ color: colors.textMuted, padding: 24, textAlign: "center" }}>暂无评估结果</div>
        ) : results.map((result) => (
          <div key={result.id} style={{ borderBottom: `1px solid ${colors.borderLight}`, padding: "12px 0" }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
              <strong>#{result.id} · {result.strategy}</strong>
              <span style={{ color: colors.textMuted, fontSize: font.xs }}>{new Date(result.created_at).toLocaleString()}</span>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 8, marginTop: 10 }}>
              {Object.entries(result.metrics || {}).map(([key, value]) => (
                <div key={key} style={{ background: colors.hover, borderRadius: 6, padding: "8px 10px" }}>
                  <div style={{ color: colors.textMuted, fontSize: font.xs }}>{key}</div>
                  <div style={{ fontWeight: 700 }}>{typeof value === "number" ? value.toFixed(4) : String(value)}</div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

