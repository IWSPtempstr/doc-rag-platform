"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { ProtectedRoute } from "@/lib/auth";
import type { Company, ConnectorStatusResponse, FinanceEvalResult, FinanceSummary } from "@/lib/types";
import { colors, font, card, btnPrimary, inputBase, btnGhost } from "@/lib/styles";

type FinanceTab = "overview" | "ingest" | "rag" | "companies";

export default function FinanceHomePage() {
  return <ProtectedRoute><FinanceHomePageInner /></ProtectedRoute>;
}

function FinanceHomePageInner() {
  const router = useRouter();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [evals, setEvals] = useState<FinanceEvalResult[]>([]);
  const [summary, setSummary] = useState<FinanceSummary | null>(null);
  const [connectors, setConnectors] = useState<ConnectorStatusResponse | null>(null);
  const [activeTab, setActiveTab] = useState<FinanceTab>("overview");
  const [ticker, setTicker] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [ashareYear, setAshareYear] = useState(String(new Date().getFullYear() - 1));
  const [message, setMessage] = useState("");
  const [announcements, setAnnouncements] = useState<any[]>([]);
  const [ragQuestion, setRagQuestion] = useState("");
  const [ragResult, setRagResult] = useState<any>(null);
  const [ragLoading, setRagLoading] = useState(false);
  const [ragError, setRagError] = useState("");

  const load = () => {
    api.listCompanies().then((rows: any) => setCompanies(rows)).catch(console.error);
    api.listFinanceEvaluationResults().then((rows: any) => setEvals(rows)).catch(() => setEvals([]));
    api.getFinanceSummary().then((row: any) => setSummary(row)).catch(() => setSummary(null));
    api.getConnectorStatus().then((row: any) => setConnectors(row)).catch(() => setConnectors(null));
  };

  useEffect(() => { load(); }, []);

  const createCompany = async () => {
    if (!ticker.trim()) return;
    try {
      await api.createCompany({ ticker, name: companyName || undefined, exchange: inferMarket(ticker) });
      setTicker("");
      setCompanyName("");
      setMessage("公司已创建");
      setActiveTab("companies");
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

  const addAndImportAshare = async () => {
    const symbol = ticker.trim();
    if (!isAshare(symbol)) {
      setMessage("请输入 6 位 A 股代码");
      return;
    }
    try {
      await api.createCompany({ ticker: symbol, name: companyName || undefined, exchange: inferMarket(symbol), industry: "A-share" });
      const filing: any = await api.importAshareFiling(symbol, { fiscal_year: Number(ashareYear) });
      setMessage(`${symbol} ${filing.fiscal_year} A 股年报已加入导入队列`);
      setTicker("");
      setCompanyName("");
      setAnnouncements([]);
      setActiveTab("companies");
      load();
    } catch (err: any) {
      setMessage(`A 股导入失败: ${err.message}`);
    }
  };

  const searchAshareAnnual = async () => {
    const symbol = ticker.trim();
    if (!isAshare(symbol)) {
      setMessage("请输入 6 位 A 股代码");
      return;
    }
    try {
      const rows: any = await api.listAshareAnnouncements(symbol, {
        keyword: `${ashareYear}年年度报告`,
        page_size: 5,
      });
      setAnnouncements(rows || []);
      setMessage(rows?.length ? `找到 ${rows.length} 条公告` : "未找到公告");
    } catch (err: any) {
      setMessage(`公告检索失败: ${err.message}`);
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

  const deleteCompany = async (symbol: string) => {
    if (!window.confirm(`确认删除 ${symbol} 及其 filings、facts、索引文档？`)) return;
    try {
      const result: any = await api.deleteCompany(symbol);
      setMessage(`${symbol} 已删除，filings ${result.filings_deleted || 0}，documents ${result.documents_deleted || 0}`);
      load();
    } catch (err: any) {
      setMessage(`删除失败: ${err.message}`);
    }
  };

  const askRag = async () => {
    if (!ragQuestion.trim()) return;
    setRagLoading(true);
    setRagError("");
    setRagResult(null);
    try {
      const result: any = await api.query(ragQuestion, 5);
      setRagResult(result);
    } catch (err: any) {
      setRagError(err.message);
    } finally {
      setRagLoading(false);
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

      <div style={tabsWrap}>
        <button style={tabButton(activeTab === "overview")} onClick={() => setActiveTab("overview")}>总览</button>
        <button style={tabButton(activeTab === "ingest")} onClick={() => setActiveTab("ingest")}>数据入口</button>
        <button style={tabButton(activeTab === "rag")} onClick={() => setActiveTab("rag")}>RAG 问答</button>
        <button style={tabButton(activeTab === "companies")} onClick={() => setActiveTab("companies")}>公司资产</button>
      </div>

      {activeTab === "overview" && (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12 }}>
            <Metric title="公司数" value={String(summary?.company_count ?? companies.length)} />
            <Metric title="Filings" value={String(summary?.filing_count ?? "-")} />
            <Metric title="公开数据集" value={String(summary?.dataset_count ?? "-")} />
            <Metric title="可评估 Cases" value={String(summary?.case_count ?? "-")} />
            <Metric title="最近评估" value={evals[0]?.strategy || "-"} />
            <Metric title="检索命中率" value={formatMetric(summary?.latest_eval?.retrieval_hit_rate ?? evals[0]?.metrics?.retrieval_hit_rate)} />
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12, marginTop: 12 }}>
            <Metric title="连接器" value={String(connectors?.connectors?.length ?? 0)} />
            <Metric title="可用数据源" value={String((connectors?.connectors || []).filter((c) => c.status === "available" || c.status === "configured" || c.status === "success").length)} />
            <Metric title="日更任务" value={String(connectors?.daily_jobs?.length ?? 0)} />
            <div style={{ ...card, marginBottom: 0, display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
              <div>
                <div style={{ color: colors.textMuted, fontSize: font.xs, marginBottom: 6 }}>数据源工作台</div>
                <div style={{ fontSize: font.md, fontWeight: 700 }}>SEC / CNINFO / AKShare / Chroma</div>
              </div>
              <button style={{ ...btnGhost, marginTop: 12, alignSelf: "flex-start" }} onClick={() => router.push("/finance/connectors")}>
                查看连接器
              </button>
            </div>
          </div>

          <div style={{ ...card, display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center" }}>
            <div>
              <h2 style={{ margin: "0 0 6px", fontSize: font.lg }}>常用操作</h2>
              <div style={{ color: colors.textSecondary, fontSize: font.sm }}>
                导入公司、问答、查看资产分别在上方 tab 中处理。
              </div>
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "flex-end" }}>
              <button style={btnGhost} onClick={() => setActiveTab("ingest")}>导入数据</button>
              <button style={btnGhost} onClick={() => setActiveTab("rag")}>RAG 问答</button>
              <button style={btnGhost} onClick={() => setActiveTab("companies")}>公司资产</button>
            </div>
          </div>

          {summary && Object.keys(summary.dataset_failure_counts || {}).length > 0 && (
            <FailurePanel summary={summary} />
          )}
        </>
      )}

      {activeTab === "ingest" && (
        <div style={card}>
          <h2 style={{ margin: "0 0 12px", fontSize: font.lg }}>数据入口</h2>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 10 }}>
            <input value={ticker} onChange={(e) => setTicker(e.target.value.toUpperCase())} placeholder="AAPL 或 600519" style={inputBase} />
            <input value={companyName} onChange={(e) => setCompanyName(e.target.value)} placeholder="公司名，可留空自动解析 SEC" style={inputBase} />
            <input value={ashareYear} onChange={(e) => setAshareYear(e.target.value)} placeholder="A股年报年份" style={inputBase} />
            <button onClick={createCompany} style={btnPrimary}>添加</button>
          </div>
          <div style={{ display: "flex", gap: 8, marginTop: 10, flexWrap: "wrap" }}>
            <button onClick={searchAshareAnnual} style={btnGhost}>搜索A股年报</button>
            <button onClick={addAndImportAshare} style={btnGhost}>添加并导入A股年报</button>
          </div>
          {announcements.length > 0 && (
            <div style={{ marginTop: 12, borderTop: `1px solid ${colors.borderLight}`, paddingTop: 10 }}>
              {announcements.slice(0, 5).map((row, idx) => (
                <div key={`${row.announcement_id || idx}`} style={{ display: "flex", justifyContent: "space-between", gap: 10, padding: "6px 0", fontSize: font.sm }}>
                  <span style={{ color: colors.text }}>{row.announcement_title}</span>
                  <span style={{ color: colors.textMuted, whiteSpace: "nowrap" }}>{row.filing_type} · {row.fiscal_year}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {activeTab === "rag" && (
        <div style={card}>
          <h2 style={{ margin: "0 0 12px", fontSize: font.lg }}>文档 RAG 问答</h2>
          <div style={{ display: "flex", gap: 10 }}>
            <input
              value={ragQuestion}
              onChange={(e) => setRagQuestion(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && askRag()}
              placeholder="输入财报或公告相关问题"
              style={{ ...inputBase, flex: 1 }}
            />
            <button onClick={askRag} disabled={ragLoading} style={{ ...btnPrimary, opacity: ragLoading ? 0.6 : 1 }}>
              {ragLoading ? "查询中..." : "提问"}
            </button>
          </div>
          {ragError && (
            <div style={{ color: colors.danger, fontSize: font.sm, marginTop: 10 }}>{ragError}</div>
          )}
          {ragResult && (
            <div style={{ marginTop: 14, borderTop: `1px solid ${colors.borderLight}`, paddingTop: 14 }}>
              <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.7, fontSize: font.sm }}>
                {ragResult.answer}
              </div>
              {ragResult.citations?.length > 0 && (
                <details style={{ marginTop: 12 }}>
                  <summary style={{ cursor: "pointer", color: colors.textSecondary, fontSize: font.sm }}>
                    引用来源 ({ragResult.citations.length})
                  </summary>
                  <div style={{ display: "grid", gap: 8, marginTop: 8 }}>
                    {ragResult.citations.map((citation: any, idx: number) => (
                      <div key={`${citation.chunk_id || idx}`} style={{ background: colors.hover, borderRadius: 6, padding: 10, fontSize: font.xs }}>
                        <div style={{ color: colors.textSecondary, marginBottom: 4 }}>
                          {citation.filename} · score {citation.score?.toFixed?.(3) || "-"}
                        </div>
                        <div style={{ color: colors.text }}>{citation.content?.slice(0, 220)}</div>
                      </div>
                    ))}
                  </div>
                </details>
              )}
            </div>
          )}
        </div>
      )}

      {activeTab === "companies" && (
        <div style={card}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, marginBottom: 12 }}>
            <h2 style={{ margin: 0, fontSize: font.lg }}>公司资产</h2>
            <button style={btnGhost} onClick={() => setActiveTab("ingest")}>添加公司</button>
          </div>
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
                      <button style={{ ...btnGhost, marginLeft: 8, color: colors.danger }} onClick={() => deleteCompany(company.ticker)}>删除</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
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

function FailurePanel({ summary }: { summary: FinanceSummary }) {
  return (
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
  );
}

function isAshare(ticker: string) {
  return /^\d{6}$/.test(ticker);
}

function inferMarket(ticker: string) {
  if (!isAshare(ticker)) return undefined;
  return ticker.startsWith("6") || ticker.startsWith("5") || ticker.startsWith("9") ? "SSE" : "SZSE";
}

const th: React.CSSProperties = { textAlign: "left", padding: "10px", fontSize: font.xs, color: colors.textMuted };
const td: React.CSSProperties = { padding: "10px", fontSize: font.sm };
const tabsWrap: React.CSSProperties = {
  display: "flex",
  gap: 8,
  flexWrap: "wrap",
  marginBottom: 16,
  borderBottom: `1px solid ${colors.border}`,
  paddingBottom: 8,
};

function tabButton(active: boolean): React.CSSProperties {
  return {
    ...btnGhost,
    background: active ? colors.primary : "transparent",
    color: active ? "#fff" : colors.textSecondary,
    borderColor: active ? colors.primary : colors.border,
    fontSize: font.sm,
    padding: "7px 16px",
  };
}
