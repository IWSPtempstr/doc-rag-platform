"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { ProtectedRoute } from "@/lib/auth";
import type { AgentRunSummary, CompanyCoverage, FinancialFact, Filing, FilingSection, MarketFact } from "@/lib/types";
import { colors, font, card, btnGhost, btnPrimary, inputBase } from "@/lib/styles";

export default function FinanceCompanyPage() {
  return <ProtectedRoute><FinanceCompanyPageInner /></ProtectedRoute>;
}

function FinanceCompanyPageInner() {
  const params = useParams();
  const router = useRouter();
  const ticker = String(params.ticker || "").toUpperCase();
  const [company, setCompany] = useState<any>(null);
  const [filings, setFilings] = useState<Filing[]>([]);
  const [sections, setSections] = useState<Record<number, FilingSection[]>>({});
  const [facts, setFacts] = useState<Record<number, FinancialFact[]>>({});
  const [coverage, setCoverage] = useState<CompanyCoverage | null>(null);
  const [marketFacts, setMarketFacts] = useState<MarketFact[]>([]);
  const [agentRuns, setAgentRuns] = useState<AgentRunSummary[]>([]);
  const [announcements, setAnnouncements] = useState<any[]>([]);
  const [message, setMessage] = useState("");
  const [ashareYear, setAshareYear] = useState(String(new Date().getFullYear() - 1));

  const load = async () => {
    try {
      const data: any = await api.getCompany(ticker);
      setCompany(data.company);
      setFilings(data.filings || []);

      const filingRows = data.filings || [];
      const sectionResults = await Promise.allSettled(
        filingRows.map((filing: Filing) => api.getFilingSections(filing.id).then((rows: any) => [filing.id, rows] as const))
      );
      const nextSections: Record<number, FilingSection[]> = {};
      sectionResults.forEach((result) => {
        if (result.status === "fulfilled") {
          const [filingId, rows] = result.value;
          nextSections[filingId] = rows || [];
        }
      });
      setSections(nextSections);

      const factResults = await Promise.allSettled(
        filingRows.map((filing: Filing) => api.getFilingFacts(filing.id).then((rows: any) => [filing.id, rows] as const))
      );
      const nextFacts: Record<number, FinancialFact[]> = {};
      factResults.forEach((result) => {
        if (result.status === "fulfilled") {
          const [filingId, rows] = result.value;
          nextFacts[filingId] = rows || [];
        }
      });
      setFacts(nextFacts);

      api.getCompanyCoverage(ticker).then((row: any) => setCoverage(row)).catch(() => setCoverage(null));
      api.listCompanyAgentRuns(ticker, 8).then((rows: any) => setAgentRuns(rows || [])).catch(() => setAgentRuns([]));
      if (isAshare(ticker)) {
        api.getMarketFacts(ticker).then((rows: any) => setMarketFacts(rows || [])).catch(() => setMarketFacts([]));
        api.listAshareAnnouncements(ticker, { keyword: `${ashareYear}年年度报告`, page_size: 10 })
          .then((rows: any) => setAnnouncements(rows || []))
          .catch(() => setAnnouncements([]));
      } else {
        setMarketFacts([]);
        setAnnouncements([]);
      }
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => { load(); }, [ticker]);

  const importLatest = async () => {
    try {
      const filing: any = await api.importFiling(ticker, {});
      setMessage(`${filing.fiscal_year} 10-K 已加入导入队列`);
      load();
    } catch (err: any) {
      setMessage(`导入失败: ${err.message}`);
    }
  };

  const importAshareAnnual = async () => {
    try {
      const filing: any = await api.importAshareFiling(ticker, { fiscal_year: Number(ashareYear) });
      setMessage(`${filing.fiscal_year} A 股年报已加入导入队列`);
      load();
    } catch (err: any) {
      setMessage(`A 股导入失败: ${err.message}`);
    }
  };

  const syncAshareFacts = async () => {
    try {
      const result: any = await api.syncAshareFacts(ticker, { fiscal_year: Number(ashareYear), provider: "akshare" });
      setMessage(`结构化财务事实已同步 ${result.upserted} 条`);
      load();
    } catch (err: any) {
      setMessage(`同步失败: ${err.message}`);
    }
  };

  const syncAshareMarket = async () => {
    try {
      const result: any = await api.syncAshareMarket(ticker, { provider: "akshare" });
      setMessage(`${ticker} 行情事实已同步 ${result.upserted} 条`);
      load();
    } catch (err: any) {
      setMessage(`行情同步失败: ${err.message}`);
    }
  };

  const deleteCompany = async () => {
    if (!window.confirm(`确认删除 ${ticker} 及其 filings、facts、索引文档？`)) return;
    try {
      await api.deleteCompany(ticker);
      router.replace("/finance");
    } catch (err: any) {
      setMessage(`删除失败: ${err.message}`);
    }
  };

  const deleteFiling = async (filing: Filing) => {
    if (!window.confirm(`确认删除 ${ticker} FY${filing.fiscal_year} ${filing.filing_type}？`)) return;
    try {
      const result: any = await api.deleteFiling(filing.id);
      setMessage(`Filing 已删除，documents ${result.documents_deleted || 0}`);
      load();
    } catch (err: any) {
      setMessage(`删除 filing 失败: ${err.message}`);
    }
  };

  if (!company) return <div style={card}>加载中...</div>;

  const isAsh = isAshare(ticker);

  return (
    <div>
      <a onClick={() => router.push("/finance")} style={{ color: colors.accent, cursor: "pointer", fontSize: font.sm }}>
        &larr; 返回财报工作台
      </a>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, margin: "12px 0 20px" }}>
        <div>
          <h1 style={{ margin: 0, fontSize: font.xxl }}>{company.ticker} · {company.name}</h1>
          <p style={{ margin: "6px 0 0", color: colors.textSecondary, fontSize: font.sm }}>
            CIK: {company.cik || "-"} · {company.exchange || "-"} · {company.industry || "-"}
          </p>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "flex-end" }}>
          <button style={btnGhost} onClick={() => router.push(`/finance/agent?ticker=${company.ticker}`)}>Agent 分析</button>
          {isAsh ? (
            <>
              <input value={ashareYear} onChange={(e) => setAshareYear(e.target.value)} style={{ ...inputBase, width: 110 }} />
              <button style={btnGhost} onClick={importAshareAnnual}>导入年报</button>
              <button style={btnGhost} onClick={syncAshareFacts}>同步事实</button>
              <button style={btnGhost} onClick={syncAshareMarket}>同步行情</button>
            </>
          ) : (
            <button style={btnPrimary} onClick={importLatest}>导入最新 10-K</button>
          )}
          <button style={{ ...btnGhost, color: colors.danger }} onClick={deleteCompany}>删除公司</button>
        </div>
      </div>

      {message && <div style={{ ...card, color: message.includes("失败") ? colors.danger : colors.success, padding: 12 }}>{message}</div>}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12 }}>
        <Metric title="Filings" value={String(coverage?.filing_count ?? filings.length)} />
        <Metric title="Documents" value={String(coverage?.document_count ?? 0)} />
        <Metric title="Sections" value={String(coverage?.section_count ?? 0)} />
        <Metric title="FinancialFact" value={String(coverage?.financial_fact_count ?? 0)} />
        <Metric title="MarketFact" value={String(coverage?.market_fact_count ?? 0)} />
        <Metric title="Chroma chunks" value={String(coverage?.chroma_chunk_count ?? 0)} />
      </div>

      {coverage?.failure_flags?.length ? (
        <div style={card}>
          <h2 style={{ margin: "0 0 10px", fontSize: font.lg }}>覆盖阻塞</h2>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {coverage.failure_flags.map((flag) => (
              <span key={flag} style={flagPill(flag)}>{flag}</span>
            ))}
          </div>
        </div>
      ) : null}

      <div style={card}>
        <h2 style={{ margin: "0 0 14px", fontSize: font.lg }}>Filings</h2>
        {filings.length === 0 ? (
          <div style={{ color: colors.textMuted, padding: 24, textAlign: "center" }}>暂无 filings</div>
        ) : filings.map((filing) => (
          <div key={filing.id} style={{ border: `1px solid ${colors.border}`, borderRadius: 8, padding: 14, marginBottom: 12 }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
              <div>
                <strong>{filing.filing_type} · FY {filing.fiscal_year}</strong>
                <div style={{ color: colors.textSecondary, fontSize: font.xs, marginTop: 4 }}>
                  {filing.accession_number || "local filing"} · {filing.status}
                </div>
                {filing.document && (
                  <div style={{ color: colors.textSecondary, fontSize: font.xs, marginTop: 4 }}>
                    文档: {filing.document.filename} · {filing.document.status} · chunks {filing.document.chunk_count}
                  </div>
                )}
              </div>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "flex-end" }}>
                {filing.document_id && (
                  <button style={btnGhost} onClick={() => router.push(`/documents/${filing.document_id}`)}>文档详情</button>
                )}
                <button style={{ ...btnGhost, color: colors.danger }} onClick={() => deleteFiling(filing)}>删除 Filing</button>
              </div>
            </div>

            {filing.metadata_json?.announcement_title && (
              <div style={{ marginTop: 10, color: colors.textSecondary, fontSize: font.xs }}>
                公告: {filing.metadata_json.announcement_title}
              </div>
            )}

            {coverage?.filings?.find((row) => row.id === filing.id)?.metadata_json?.auto_fact_sync && (
              <div style={{ marginTop: 10, color: colors.textSecondary, fontSize: font.xs }}>
                自动同步: {JSON.stringify(coverage.filings.find((row) => row.id === filing.id)?.metadata_json?.auto_fact_sync)}
              </div>
            )}

            <div style={{ marginTop: 12, display: "grid", gap: 10 }}>
              <SectionList title="章节" rows={(sections[filing.id] || []).slice(0, 5)} />
              <FactList title="财务事实" rows={(facts[filing.id] || []).slice(0, 8)} />
            </div>
          </div>
        ))}
      </div>

      {isAsh && (
        <>
          <div style={card}>
            <h2 style={{ margin: "0 0 14px", fontSize: font.lg }}>公告</h2>
            {announcements.length === 0 ? (
              <div style={{ color: colors.textMuted, padding: 24, textAlign: "center" }}>暂无公告</div>
            ) : announcements.map((row, idx) => (
              <div key={row.announcement_id || idx} style={{ borderBottom: `1px solid ${colors.borderLight}`, padding: "10px 0" }}>
                <strong style={{ fontSize: font.sm }}>{row.announcement_title}</strong>
                <div style={{ color: colors.textSecondary, fontSize: font.xs, marginTop: 4 }}>
                  {row.filing_type} · FY {row.fiscal_year} · {row.published_at ? new Date(row.published_at).toLocaleString() : "-"}
                </div>
              </div>
            ))}
          </div>

          <div style={card}>
            <h2 style={{ margin: "0 0 14px", fontSize: font.lg }}>行情事实</h2>
            {marketFacts.length === 0 ? (
              <div style={{ color: colors.textMuted, padding: 24, textAlign: "center" }}>暂无行情事实</div>
            ) : (
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ borderBottom: `1px solid ${colors.border}` }}>
                    <th style={th}>日期</th>
                    <th style={th}>指标</th>
                    <th style={th}>值</th>
                    <th style={th}>来源</th>
                  </tr>
                </thead>
                <tbody>
                  {marketFacts.slice(0, 12).map((fact) => (
                    <tr key={fact.id} style={{ borderBottom: `1px solid ${colors.borderLight}` }}>
                      <td style={td}>{fact.trade_date}</td>
                      <td style={td}>{fact.label}</td>
                      <td style={td}>{fact.value ?? "-"}</td>
                      <td style={td}>{fact.source}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}

      <div style={card}>
        <h2 style={{ margin: "0 0 14px", fontSize: font.lg }}>最近 AgentRun</h2>
        {agentRuns.length === 0 ? (
          <div style={{ color: colors.textMuted, padding: 24, textAlign: "center" }}>暂无运行记录</div>
        ) : agentRuns.map((run) => (
          <div key={run.id} style={{ borderBottom: `1px solid ${colors.borderLight}`, padding: "10px 0" }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
              <strong style={{ fontSize: font.sm }}>{run.question}</strong>
              <span style={{ color: run.status === "completed" ? colors.success : run.status === "failed" ? colors.danger : colors.warn, fontSize: font.xs }}>
                {run.status}
              </span>
            </div>
            <div style={{ color: colors.textSecondary, fontSize: font.xs, marginTop: 4 }}>
              {run.mode} · {run.created_at ? new Date(run.created_at).toLocaleString() : "-"}
              {run.verification?.passed !== undefined && <> · verifier {run.verification.passed ? "passed" : "failed"}</>}
            </div>
            {run.answer_preview && (
              <div style={{ color: colors.text, fontSize: font.xs, marginTop: 6, whiteSpace: "pre-wrap" }}>
                {run.answer_preview}
              </div>
            )}
          </div>
        ))}
      </div>
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

function SectionList({ title, rows }: { title: string; rows: FilingSection[] }) {
  return (
    <div>
      <div style={{ color: colors.textSecondary, fontSize: font.sm, fontWeight: 700, marginBottom: 8 }}>{title}</div>
      {rows.length === 0 ? (
        <div style={{ color: colors.textMuted, fontSize: font.xs }}>暂无章节</div>
      ) : rows.map((section) => (
        <details key={section.id} style={{ background: colors.hover, borderRadius: 6, padding: "8px 10px", marginBottom: 8 }}>
          <summary style={{ cursor: "pointer", fontSize: font.sm, fontWeight: 600 }}>
            Item {section.item_code} · {section.title}
          </summary>
          <p style={{ whiteSpace: "pre-wrap", fontSize: font.xs, lineHeight: 1.6 }}>{section.content_preview}</p>
        </details>
      ))}
    </div>
  );
}

function FactList({ title, rows }: { title: string; rows: FinancialFact[] }) {
  return (
    <div>
      <div style={{ color: colors.textSecondary, fontSize: font.sm, fontWeight: 700, marginBottom: 8 }}>{title}</div>
      {rows.length === 0 ? (
        <div style={{ color: colors.textMuted, fontSize: font.xs }}>暂无事实</div>
      ) : rows.map((fact) => (
        <div key={fact.id} style={{ background: colors.hover, borderRadius: 6, padding: "8px 10px", marginBottom: 8, fontSize: font.xs }}>
          <strong>{fact.label}</strong> · {fact.metric} · {fact.value ?? "-"} {fact.unit || ""}
          <div style={{ color: colors.textSecondary, marginTop: 4 }}>
            {fact.source} · {fact.period || "-"}
          </div>
        </div>
      ))}
    </div>
  );
}

function flagPill(flag: string): React.CSSProperties {
  const color = flag.includes("missing") ? colors.warn : colors.danger;
  return {
    display: "inline-block",
    padding: "4px 8px",
    borderRadius: 6,
    background: color,
    color: "#fff",
    fontSize: font.xs,
    fontWeight: 700,
  };
}

function isAshare(ticker: string) {
  return /^\d{6}$/.test(ticker);
}

const th: React.CSSProperties = { textAlign: "left", padding: "10px", fontSize: font.xs, color: colors.textMuted, fontWeight: 600 };
const td: React.CSSProperties = { padding: "10px", fontSize: font.sm };
