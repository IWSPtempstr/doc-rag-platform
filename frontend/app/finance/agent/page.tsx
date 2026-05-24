"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { ProtectedRoute } from "@/lib/auth";
import type { AgentRunSummary, Company, FinanceAgentResult } from "@/lib/types";
import { colors, font, card, btnGhost, btnPrimary, inputBase } from "@/lib/styles";

export default function FinanceAgentPage() {
  return <ProtectedRoute><Suspense><FinanceAgentPageInner /></Suspense></ProtectedRoute>;
}

function FinanceAgentPageInner() {
  const searchParams = useSearchParams();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [ticker, setTicker] = useState(searchParams.get("ticker") || "");
  const [question, setQuestion] = useState("结合公告、财务事实、行情热度和市场情绪，解释这家公司今天需要关注的变化。");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<FinanceAgentResult | null>(null);
  const [history, setHistory] = useState<AgentRunSummary[]>([]);
  const [error, setError] = useState("");

  const loadHistory = (targetTicker?: string) => {
    api.listFinanceAgentRuns({ company_ticker: targetTicker || ticker || undefined, limit: 30 })
      .then((rows: any) => setHistory(rows || []))
      .catch(() => setHistory([]));
  };

  useEffect(() => {
    api.listCompanies().then((rows: any) => {
      setCompanies(rows);
      if (!ticker && rows[0]) setTicker(rows[0].ticker);
    }).catch(console.error);
  }, []);

  useEffect(() => {
    loadHistory(ticker || undefined);
  }, [ticker]);

  const run = async () => {
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const response: any = await api.queryFinanceAgent({
        company_ticker: ticker,
        question,
        mode: "full",
      });
      setResult(response);
      loadHistory(ticker);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const removeRun = async (runId: number) => {
    if (!window.confirm("确认删除这条分析记录？")) return;
    try {
      await api.deleteFinanceAgentRun(runId);
      setHistory((rows) => rows.filter((row) => row.id !== runId));
    } catch (err: any) {
      setError(`删除失败: ${err.message}`);
    }
  };

  return (
    <div>
      <h1 style={{ margin: "0 0 6px", fontSize: font.xxl }}>A 股个性化分析</h1>
      <p style={{ margin: "0 0 20px", color: colors.textSecondary, fontSize: font.sm }}>
        中心化 MAS：公告检索、财务事实、行情事实、情绪解释、校验轨迹。
      </p>

      <div style={card}>
        <div style={{ display: "grid", gridTemplateColumns: "180px 1fr", gap: 10, marginBottom: 12 }}>
          <select value={ticker} onChange={(e) => setTicker(e.target.value)} style={inputBase}>
            <option value="">选择公司</option>
            {companies.map((company) => (
              <option key={company.id} value={company.ticker}>{company.ticker} · {company.name}</option>
            ))}
          </select>
          <input value={question} onChange={(e) => setQuestion(e.target.value)} style={inputBase} />
        </div>
        <button onClick={run} disabled={loading || !ticker || !question} style={{ ...btnPrimary, opacity: loading ? 0.6 : 1 }}>
          {loading ? "分析中..." : "运行 Agent"}
        </button>
      </div>

      <div style={card}>
        <h2 style={{ margin: "0 0 12px", fontSize: font.lg }}>历史查询记录</h2>
        {history.length === 0 ? (
          <div style={{ color: colors.textMuted, fontSize: font.sm }}>暂无历史分析记录。</div>
        ) : (
          <div style={{ display: "grid", gap: 10 }}>
            {history.map((run) => (
              <div key={run.id} style={{ border: `1px solid ${colors.borderLight}`, borderRadius: 8, padding: 12 }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                  <div>
                    <strong style={{ fontSize: font.sm }}>{run.company?.ticker || ticker || "-"} · {run.question}</strong>
                    <div style={{ color: colors.textSecondary, fontSize: font.xs, marginTop: 4 }}>
                      {run.status} · {run.created_at ? new Date(run.created_at).toLocaleString() : "-"}
                    </div>
                  </div>
                  <button style={{ ...btnGhost, color: colors.danger }} onClick={() => removeRun(run.id)}>删除</button>
                </div>
                {run.answer_preview && (
                  <div style={{ color: colors.textSecondary, fontSize: font.xs, marginTop: 8, whiteSpace: "pre-wrap", lineHeight: 1.6 }}>
                    {run.answer_preview}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {error && <div style={{ ...card, color: colors.danger }}>{error}</div>}

      {result && (
        <>
          <div style={card}>
            <h2 style={{ margin: "0 0 10px", fontSize: font.lg }}>分析结论</h2>
            <p style={{ whiteSpace: "pre-wrap", lineHeight: 1.7 }}>{result.answer}</p>
            <div style={{ color: result.verification?.passed ? colors.success : colors.warn, fontSize: font.sm }}>
              {result.verification?.passed ? "已通过一致性校验" : "需人工复核"}
            </div>
          </div>

          <details style={card}>
            <summary style={{ cursor: "pointer", fontWeight: 700, fontSize: font.md }}>查看依据与技术细节</summary>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 12, marginTop: 14 }}>
              <Panel title="结构化事实" items={result.facts} />
              <Panel title="确定性计算" items={result.calculations} />
              <Panel title="引用片段" items={result.citations} />
            </div>
            <div style={{ marginTop: 14 }}>
              <h2 style={{ margin: "0 0 10px", fontSize: font.md }}>执行轨迹</h2>
              {result.steps.map((step) => (
                <div key={step.id} style={{ borderBottom: `1px solid ${colors.borderLight}`, padding: "8px 0", fontSize: font.sm }}>
                  <strong>{step.node_name}</strong>
                  <span style={{ color: colors.textSecondary }}> · {step.status} · {step.duration_ms}ms</span>
                  <pre style={{ whiteSpace: "pre-wrap", fontSize: font.xs, color: colors.textSecondary }}>
                    {JSON.stringify(step.output_json, null, 2)}
                  </pre>
                </div>
              ))}
            </div>
          </details>
        </>
      )}
    </div>
  );
}

function Panel({ title, items }: { title: string; items: any[] }) {
  return (
    <div style={card}>
      <h3 style={{ margin: "0 0 8px", fontSize: font.md }}>{title}</h3>
      {items.length === 0 ? <div style={{ color: colors.textMuted, fontSize: font.sm }}>暂无</div> : items.slice(0, 5).map((item, idx) => (
        <pre key={idx} style={{ whiteSpace: "pre-wrap", fontSize: font.xs, color: colors.textSecondary }}>
          {JSON.stringify(item, null, 2)}
        </pre>
      ))}
    </div>
  );
}
