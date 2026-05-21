"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { ProtectedRoute } from "@/lib/auth";
import type { Company, FinanceEvalResult, FinanceSummary } from "@/lib/types";
import { colors, radius, font, card, btnPrimary, inputBase, btnGhost } from "@/lib/styles";

export default function FinanceHomePage() {
  return <ProtectedRoute><FinanceHomePageInner /></ProtectedRoute>;
}

function FinanceHomePageInner() {
  const router = useRouter();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [evals, setEvals] = useState<FinanceEvalResult[]>([]);
  const [summary, setSummary] = useState<FinanceSummary | null>(null);
  const [ticker, setTicker] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [ashareYear, setAshareYear] = useState(String(new Date().getFullYear() - 1));
  const [message, setMessage] = useState("");

  const load = () => {
    api.listCompanies().then((rows: any) => setCompanies(rows)).catch(console.error);
    api.listFinanceEvaluationResults().then((rows: any) => setEvals(rows)).catch(() => setEvals([]));
    api.getFinanceSummary().then((row: any) => setSummary(row)).catch(() => setSummary(null));
  };

  useEffect(() => { load(); }, []);

  const createCompany = async () => {
    if (!ticker.trim()) return;
    try {
      await api.createCompany({ ticker, name: companyName || undefined });
      setTicker("");
      setCompanyName("");
      setMessage("公司已创建");
      load();
    } catch (err: any) {
      setMessage(`创建失败: ${err.message}`);
    }
  };

  const importLatest = async (symbol: string) => {
    try {
      const filing: any = await api.importFiling(symbol, {});
      setMessage(`${symbol} ${filing.fiscal_year} 10-K 已加入导入队列`);
      load();
    } catch (err: any) {
      setMessage(`导入失败: ${err.message}`);
    }
  };

  const importAshareAnnual = async (symbol: string) => {
    try {
      const filing: any = await api.importAshareFiling(symbol, { fiscal_year: Number(ashareYear) });
      setMessage(`${symbol} ${filing.fiscal_year} A 股年报已加入导入队列`);
      load();
    } catch (err: any) {
      setMessage(`A 股导入失败: ${err.message}`);
    }
  };

  const syncAshareMarket = async (symbol: string) => {
    try {
      const result: any = await api.syncAshareMarket(symbol, {});
      setMessage(`${symbol} 行情事实已同步 ${result.upserted} 条`);
    } catch (err: any) {
      setMessage(`行情同步失败: ${err.message}`);
    }
  };

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: font.xxl }}>财报分析工作台</h1>
          <p style={{ margin: "6px 0 0", color: colors.textSecondary, fontSize: font.sm }}>
            SEC 10-K / A 股公告导入、证据型 RAG、多步 Agent 分析与评估
          </p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button style={btnGhost} onClick={() => router.push("/finance/agent")}>Agent 分析</button>
          <button style={btnGhost} onClick={() => router.push("/finance/evaluations")}>评估</button>
        </div>
      </div>

      {message && (
        <div style={{ ...card, padding: "10px 14px", color: message.includes("失败") ? colors.danger : colors.success }}>
          {message}
        </div>
      )}

      <div style={card}>
        <h2 style={{ margin: "0 0 12px", fontSize: font.lg }}>添加公司</h2>
        <div style={{ display: "grid", gridTemplateColumns: "160px 1fr 120px auto", gap: 10 }}>
          <input value={ticker} onChange={(e) => setTicker(e.target.value.toUpperCase())} placeholder="Ticker, 如 AAPL" style={inputBase} />
          <input value={companyName} onChange={(e) => setCompanyName(e.target.value)} placeholder="公司名，可留空自动解析 SEC" style={inputBase} />
          <input value={ashareYear} onChange={(e) => setAshareYear(e.target.value)} placeholder="A股年报年份" style={inputBase} />
          <button onClick={createCompany} style={btnPrimary}>添加</button>
        </div>
      </div>

      <div style={card}>
        <h2 style={{ margin: "0 0 12px", fontSize: font.lg }}>公司与 10-K</h2>
        {companies.length === 0 ? (
          <div style={{ color: colors.textMuted, fontSize: font.sm, padding: 24, textAlign: "center" }}>
            还没有公司。添加 ticker 后可导入最新 10-K。
          </div>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: `1px solid ${colors.border}` }}>
                <th style={th}>Ticker</th>
                <th style={th}>公司</th>
                <th style={th}>市场</th>
                <th style={th}>CIK</th>
                <th style={th}>Filings</th>
                <th style={th}>操作</th>
              </tr>
            </thead>
            <tbody>
              {companies.map((company) => (
                <tr key={company.id} style={{ borderBottom: `1px solid ${colors.borderLight}` }}>
                  <td style={td}><strong>{company.ticker}</strong></td>
                  <td style={{ ...td, cursor: "pointer", color: colors.accent }} onClick={() => router.push(`/finance/companies/${company.ticker}`)}>
                    {company.name}
                  </td>
                  <td style={td}>{company.exchange || (isAshare(company.ticker) ? "CN" : "US")}</td>
                  <td style={td}>{company.cik || "-"}</td>
                  <td style={td}>{company.filing_count}</td>
                  <td style={td}>
                    {isAshare(company.ticker) ? (
                      <>
                        <button style={{ ...btnGhost, marginRight: 8 }} onClick={() => importAshareAnnual(company.ticker)}>导入A股年报</button>
                        <button style={{ ...btnGhost, marginRight: 8 }} onClick={() => syncAshareMarket(company.ticker)}>同步行情</button>
                      </>
                    ) : (
                      <button style={{ ...btnGhost, marginRight: 8 }} onClick={() => importLatest(company.ticker)}>导入最新 10-K</button>
                    )}
                    <button style={btnGhost} onClick={() => router.push(`/finance/companies/${company.ticker}`)}>详情</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12 }}>
        <Metric title="公司数" value={String(summary?.company_count ?? companies.length)} />
        <Metric title="Filings" value={String(summary?.filing_count ?? "-")} />
        <Metric title="公开数据集" value={String(summary?.dataset_count ?? "-")} />
        <Metric title="可评估 Cases" value={String(summary?.case_count ?? "-")} />
        <Metric title="最近评估" value={evals[0]?.strategy || "-"} />
        <Metric title="检索命中率" value={formatMetric(summary?.latest_eval?.retrieval_hit_rate ?? evals[0]?.metrics?.retrieval_hit_rate)} />
      </div>

      {summary && Object.keys(summary.dataset_failure_counts || {}).length > 0 && (
        <div style={card}>
          <h2 style={{ margin: "0 0 12px", fontSize: font.lg }}>阻塞原因</h2>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 8 }}>
            {Object.entries(summary.dataset_failure_counts).map(([reason, count]) => (
              <div key={reason} style={{ background: colors.hover, borderRadius: 6, padding: "8px 10px" }}>
                <div style={{ color: colors.textMuted, fontSize: font.xs, wordBreak: "break-word" }}>{reason}</div>
                <div style={{ fontWeight: 700 }}>{count}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function Metric({ title, value }: { title: string; value: string }) {
  return (
    <div style={{ ...card, marginBottom: 0 }}>
      <div style={{ color: colors.textMuted, fontSize: font.xs, marginBottom: 6 }}>{title}</div>
      <div style={{ fontSize: font.xl, fontWeight: 700 }}>{value}</div>
    </div>
  );
}

function formatMetric(value: any) {
  return typeof value === "number" ? `${(value * 100).toFixed(1)}%` : "-";
}

function isAshare(ticker: string) {
  return /^\d{6}$/.test(ticker);
}

const th: React.CSSProperties = { textAlign: "left", padding: "10px", fontSize: font.xs, color: colors.textMuted };
const td: React.CSSProperties = { padding: "10px", fontSize: font.sm };
