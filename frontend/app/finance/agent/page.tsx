"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { ProtectedRoute } from "@/lib/auth";
import type { Company, FinanceAgentResult } from "@/lib/types";
import { colors, font, card, btnPrimary, inputBase } from "@/lib/styles";

export default function FinanceAgentPage() {
  return <ProtectedRoute><Suspense><FinanceAgentPageInner /></Suspense></ProtectedRoute>;
}

function FinanceAgentPageInner() {
  const searchParams = useSearchParams();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [ticker, setTicker] = useState(searchParams.get("ticker") || "");
  const [question, setQuestion] = useState("Summarize revenue trend and key risks from the latest 10-K.");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<FinanceAgentResult | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.listCompanies().then((rows: any) => {
      setCompanies(rows);
      if (!ticker && rows[0]) setTicker(rows[0].ticker);
    }).catch(console.error);
  }, []);

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
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h1 style={{ margin: "0 0 6px", fontSize: font.xxl }}>Agent 财务分析师</h1>
      <p style={{ margin: "0 0 20px", color: colors.textSecondary, fontSize: font.sm }}>
        中心化 MAS：检索、指标抽取、确定性计算、分析写作、校验。
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

      {error && <div style={{ ...card, color: colors.danger }}>{error}</div>}

      {result && (
        <>
          <div style={card}>
            <h2 style={{ margin: "0 0 10px", fontSize: font.lg }}>分析结果</h2>
            <p style={{ whiteSpace: "pre-wrap", lineHeight: 1.7 }}>{result.answer}</p>
            <div style={{ color: result.verification?.passed ? colors.success : colors.warn, fontSize: font.sm }}>
              Verifier: {result.verification?.passed ? "passed" : "needs review"} · citation coverage {result.verification?.citation_coverage ?? 0}
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 12 }}>
            <Panel title="Facts" items={result.facts} />
            <Panel title="Calculations" items={result.calculations} />
            <Panel title="Citations" items={result.citations} />
          </div>

          <div style={card}>
            <h2 style={{ margin: "0 0 10px", fontSize: font.lg }}>执行轨迹</h2>
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

