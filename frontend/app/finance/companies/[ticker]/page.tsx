"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { ProtectedRoute, useAuth } from "@/lib/auth";
import type { AgentRunSummary, CompanyCoverage, CompanyResearchSummary, FinancialFact, Filing, FilingSection, MarketFact, SentimentFact } from "@/lib/types";
import { colors, font, card, btnGhost, inputBase } from "@/lib/styles";
import { isAshareLikeTicker, normalizeAshareTicker } from "@/lib/ashare";

export default function FinanceCompanyPage() {
  return <ProtectedRoute><FinanceCompanyPageInner /></ProtectedRoute>;
}

function FinanceCompanyPageInner() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { workspaces } = useAuth();
  const ticker = normalizeAshareTicker(String(params.ticker || "").toUpperCase());
  const [company, setCompany] = useState<any>(null);
  const [filings, setFilings] = useState<Filing[]>([]);
  const [sections, setSections] = useState<Record<number, FilingSection[]>>({});
  const [facts, setFacts] = useState<Record<number, FinancialFact[]>>({});
  const [coverage, setCoverage] = useState<CompanyCoverage | null>(null);
  const [researchSummary, setResearchSummary] = useState<CompanyResearchSummary | null>(null);
  const [marketFacts, setMarketFacts] = useState<MarketFact[]>([]);
  const [sentiment, setSentiment] = useState<SentimentFact[]>([]);
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
      api.getCompanyResearchSummary(ticker).then((row: any) => setResearchSummary(row)).catch(() => setResearchSummary(null));
      api.listCompanyAgentRuns(ticker, 8).then((rows: any) => setAgentRuns(rows || [])).catch(() => setAgentRuns([]));
      api.getSentimentFacts({ limit: 2 }).then((rows: any) => setSentiment(rows || [])).catch(() => setSentiment([]));
      if (isAshareLikeTicker(ticker)) {
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

  const handleResearchAction = async (key: string) => {
    if (key === "import_annual_report") return importAshareAnnual();
    if (key === "sync_financial_facts") return syncAshareFacts();
    if (key === "sync_market_facts") return syncAshareMarket();
    if (key === "search_announcements") {
      setMessage("正在检索公告...");
      try {
        const rows: any = await api.listAshareAnnouncements(ticker, { keyword: `${ashareYear}年年度报告`, page_size: 10 });
        setAnnouncements(rows || []);
        setMessage(rows?.length ? `找到 ${rows.length} 条公告` : "未找到公告，可尝试调整年份");
      } catch (err: any) {
        setMessage(`公告检索失败: ${err.message}`);
      }
      return;
    }
    if (key === "sync_market_sentiment" || key === "check_connectors") {
      router.push("/finance/connectors");
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

  const isAsh = isAshareLikeTicker(ticker);
  const briefContext = searchParams.get("from") === "brief"
    ? {
        date: searchParams.get("date") || "-",
        section: searchParams.get("section") || "-",
        rank: searchParams.get("rank") || "",
      }
    : null;
  const latestMarketFacts = marketFacts.slice(0, 4);
  const latestSentiment = sentiment[0] || null;
  const role = workspaces[0]?.role || "user";
  const isAdmin = role === "admin" || role === "owner";

  return (
    <div>
      <a onClick={() => router.push("/finance")} style={{ color: colors.accent, cursor: "pointer", fontSize: font.sm }}>
        &larr; 返回 A 股工作台
      </a>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, margin: "12px 0 20px" }}>
        <div>
          <h1 style={{ margin: 0, fontSize: font.xxl }}>{company.ticker} · {company.name}</h1>
          <p style={{ margin: "6px 0 0", color: colors.textSecondary, fontSize: font.sm }}>
            CIK: {company.cik || "-"} · {company.exchange || "-"} · {company.industry || "-"}
          </p>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "flex-end" }}>
          <button style={btnGhost} onClick={() => router.push(`/finance/agent?ticker=${company.ticker}`)}>个性化分析</button>
          {isAdmin && isAsh ? (
            <>
              <input value={ashareYear} onChange={(e) => setAshareYear(e.target.value)} style={{ ...inputBase, width: 110 }} />
              <button style={btnGhost} onClick={importAshareAnnual}>导入年报</button>
              <button style={btnGhost} onClick={syncAshareFacts}>同步事实</button>
              <button style={btnGhost} onClick={syncAshareMarket}>同步行情</button>
            </>
          ) : null}
          {isAdmin && <button style={{ ...btnGhost, color: colors.danger }} onClick={deleteCompany}>删除公司</button>}
        </div>
      </div>

      {message && <div style={{ ...card, color: message.includes("失败") ? colors.danger : colors.success, padding: 12 }}>{message}</div>}

      {briefContext && (
        <div style={{ ...card, borderColor: colors.accent, background: colors.selected }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
            <strong>来自今日简报</strong>
            <span style={{ color: colors.textSecondary, fontSize: font.sm }}>
              {briefContext.date} · {briefContext.section === "watchlist" ? "关注公司" : "热点补充"}
              {briefContext.rank ? ` · 热度 #${briefContext.rank}` : ""}
            </span>
          </div>
        </div>
      )}

      {isAsh && researchSummary && (
        <ResearchSummaryPanel summary={researchSummary} onAction={handleResearchAction} />
      )}

      {isAsh && (
        <div style={card}>
          <h2 style={{ margin: "0 0 14px", fontSize: font.lg }}>今日概览</h2>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))", gap: 12 }}>
            <OverviewBlock
              title="最新公告"
              value={announcements[0]?.announcement_title || "暂无公告"}
              detail={announcements[0]?.published_at ? new Date(announcements[0].published_at).toLocaleString() : "公告入口可检索年报与公告"}
            />
            <OverviewBlock
              title="财务要点"
              value={summarizeFinancialFacts(facts, researchSummary)}
              detail={(researchSummary?.available_signals?.financial_fact_count || 0) > 0 ? "来自已同步的结构化财务事实" : "缺少结构化财务事实，不能判断收入、利润、资产负债变化"}
            />
            <OverviewBlock
              title="行情热度"
              value={formatMarketFactSummary(latestMarketFacts, researchSummary)}
              detail={latestMarketFacts.length ? latestMarketFacts.map((fact) => `${displayMarketLabel(fact.metric, fact.label)}: ${formatNumber(fact.value)}${fact.unit === "score" ? "" : fact.unit || ""}`).join("；") : "可同步行情；若只来自热榜，只能作为关注度信号"}
            />
            <OverviewBlock
              title="市场情绪"
              value={latestSentiment ? `${latestSentiment.label || "unknown"} · ${formatNumber(latestSentiment.score)}` : "暂无情绪事实"}
              detail={latestSentiment ? `${latestSentiment.trade_date} · ${latestSentiment.source}` : "由日更任务同步市场级 SentimentFact"}
            />
            <OverviewBlock
              title="最近分析"
              value={agentRuns[0]?.status ? `${agentRuns[0].status}` : "暂无 AgentRun"}
              detail={agentRuns[0]?.question || "可从个性化分析入口生成研究辅助结果"}
            />
          </div>
        </div>
      )}

      {isAdmin && (
        <>
          <details style={card}>
            <summary style={{ cursor: "pointer", fontWeight: 700, fontSize: font.md }}>数据覆盖与索引诊断</summary>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12, marginTop: 14 }}>
              <Metric title="Filings" value={String(coverage?.filing_count ?? filings.length)} />
              <Metric title="Documents" value={String(coverage?.document_count ?? 0)} />
              <Metric title="Sections" value={String(coverage?.section_count ?? 0)} />
              <Metric title="FinancialFact" value={String(coverage?.financial_fact_count ?? 0)} />
              <Metric title="MarketFact" value={String(coverage?.market_fact_count ?? 0)} />
              <Metric title="Chroma chunks" value={String(coverage?.chroma_chunk_count ?? 0)} />
            </div>
            {coverage?.failure_flags?.length ? (
              <div style={{ marginTop: 14 }}>
                <h2 style={{ margin: "0 0 10px", fontSize: font.md }}>覆盖阻塞</h2>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {coverage.failure_flags.map((flag) => (
                    <span key={flag} style={flagPill(flag)}>{flag}</span>
                  ))}
                </div>
              </div>
            ) : null}
          </details>

          <div style={card}>
            <h2 style={{ margin: "0 0 14px", fontSize: font.lg }}>数据资产</h2>
            {filings.length === 0 ? (
              <EmptyState title="还没有导入年报" detail="缺少年报资产时，系统不能做公告引用、章节检索或基本面解释。" action="导入年报" onAction={importAshareAnnual} />
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
                    <button style={{ ...btnGhost, color: colors.danger }} onClick={() => deleteFiling(filing)}>删除资产</button>
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
        </>
      )}

      {isAsh && (
        <>
          <div style={card}>
            <h2 style={{ margin: "0 0 14px", fontSize: font.lg }}>公告</h2>
            {announcements.length === 0 ? (
              <EmptyState title="未检索到公告" detail="当前页面没有可展示公告，先搜索年报公告或调整年份后再导入。" action="搜索公告" onAction={() => handleResearchAction("search_announcements")} />
            ) : announcements.map((row, idx) => (
              <div key={row.announcement_id || idx} style={{ borderBottom: `1px solid ${colors.borderLight}`, padding: "10px 0" }}>
                <strong style={{ fontSize: font.sm }}>{row.announcement_title}</strong>
                <div style={{ color: colors.textSecondary, fontSize: font.xs, marginTop: 4 }}>
                  {row.filing_type} · FY {row.fiscal_year} · {row.published_at ? new Date(row.published_at).toLocaleString() : "-"}
                </div>
              </div>
            ))}
          </div>

          {isAdmin && <div style={card}>
            <h2 style={{ margin: "0 0 14px", fontSize: font.lg }}>行情事实</h2>
            {marketFacts.length === 0 ? (
              <EmptyState title="还没有行情或热度事实" detail="缺少行情事实时，只能依赖简报热榜，不能解释价格、成交额或热度变化。" action="同步行情热度" onAction={syncAshareMarket} />
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
          </div>}
        </>
      )}

      <div style={card}>
        <h2 style={{ margin: "0 0 14px", fontSize: font.lg }}>最近分析记录</h2>
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
              {isAdmin && run.verification?.passed !== undefined && <> · verifier {run.verification.passed ? "passed" : "failed"}</>}
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

const th: React.CSSProperties = { textAlign: "left", padding: "10px", fontSize: font.xs, color: colors.textMuted, fontWeight: 600 };
const td: React.CSSProperties = { padding: "10px", fontSize: font.sm };
const tag: React.CSSProperties = {
  display: "inline-block",
  padding: "4px 8px",
  borderRadius: 6,
  background: colors.surface,
  border: `1px solid ${colors.borderLight}`,
  color: colors.textSecondary,
  fontSize: font.xs,
};

function OverviewBlock({ title, value, detail }: { title: string; value: string; detail: string }) {
  return (
    <div style={{ border: `1px solid ${colors.borderLight}`, borderRadius: 8, padding: 12, background: colors.hover }}>
      <div style={{ color: colors.textMuted, fontSize: font.xs, marginBottom: 6 }}>{title}</div>
      <strong style={{ display: "block", fontSize: font.sm, marginBottom: 6 }}>{value}</strong>
      <div style={{ color: colors.textSecondary, fontSize: font.xs, lineHeight: 1.5 }}>{detail}</div>
    </div>
  );
}

function ResearchSummaryPanel({ summary, onAction }: { summary: CompanyResearchSummary; onAction: (key: string) => void }) {
  const hasMissing = summary.missing_items.length > 0;
  return (
    <div style={{ ...card, borderColor: hasMissing ? colors.warn : colors.border }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap", marginBottom: 12 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: font.lg }}>{hasMissing ? "数据不足研究摘要" : "研究摘要"}</h2>
          <div style={{ color: colors.textSecondary, fontSize: font.xs, marginTop: 4 }}>
            用现有数据说明能判断什么、不能判断什么，不用热度替代财务事实。
          </div>
        </div>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", justifyContent: "flex-end" }}>
          {summary.coverage_tags.map((tagText) => <span key={tagText} style={tag}>{tagText}</span>)}
        </div>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12 }}>
        <InfoList title="当前能判断" items={summary.can_infer} />
        <InfoList title="当前不能判断" items={summary.cannot_infer.length ? summary.cannot_infer : ["公告、财务、行情与情绪覆盖较完整。"]} />
        <div style={{ border: `1px solid ${colors.borderLight}`, borderRadius: 8, padding: 12, background: colors.hover }}>
          <div style={{ color: colors.textMuted, fontSize: font.xs, marginBottom: 8 }}>补全动作</div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {summary.next_actions.slice(0, 5).map((action) => (
              <button key={action.key} style={btnGhost} onClick={() => onAction(action.key)}>{action.label}</button>
            ))}
          </div>
        </div>
      </div>
      {Object.keys(summary.failure_reasons || {}).length > 0 && (
        <details style={{ marginTop: 12 }}>
          <summary style={{ cursor: "pointer", color: colors.textSecondary, fontSize: font.sm }}>查看缺失原因</summary>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
            {Object.entries(summary.failure_reasons).map(([key, value]) => (
              <span key={key} style={tag}>{failureLabel(key)}：{value}</span>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

function InfoList({ title, items }: { title: string; items: string[] }) {
  return (
    <div style={{ border: `1px solid ${colors.borderLight}`, borderRadius: 8, padding: 12, background: colors.hover }}>
      <div style={{ color: colors.textMuted, fontSize: font.xs, marginBottom: 8 }}>{title}</div>
      <ul style={{ margin: 0, paddingLeft: 18, color: colors.textSecondary, fontSize: font.xs, lineHeight: 1.7 }}>
        {items.slice(0, 4).map((item) => <li key={item}>{item}</li>)}
      </ul>
    </div>
  );
}

function EmptyState({ title, detail, action, onAction }: { title: string; detail: string; action?: string; onAction?: () => void }) {
  return (
    <div style={{ border: `1px dashed ${colors.border}`, borderRadius: 8, padding: 18, color: colors.textSecondary, background: colors.hover }}>
      <strong style={{ display: "block", color: colors.text, marginBottom: 6 }}>{title}</strong>
      <div style={{ fontSize: font.sm, lineHeight: 1.6 }}>{detail}</div>
      {action && onAction && <button style={{ ...btnGhost, marginTop: 10 }} onClick={onAction}>{action}</button>}
    </div>
  );
}

function formatNumber(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return Number(value).toFixed(2);
}

function displayMarketLabel(metric: string, label: string) {
  if (metric === "heat_score") return "市场热度";
  return label || metric;
}

function formatMarketFactSummary(rows: MarketFact[], summary?: CompanyResearchSummary | null) {
  const heat = rows.find((fact) => fact.metric === "heat_score");
  if (heat) return `市场热度 ${formatNumber(heat.value)}`;
  const fallbackHeat = summary?.available_signals?.heat_score;
  if (fallbackHeat !== null && fallbackHeat !== undefined) return `热榜热度 ${formatNumber(Number(fallbackHeat))}`;
  return rows.length ? `${rows.length} 条行情事实` : "暂无行情事实";
}

function summarizeFinancialFacts(factsByFiling: Record<number, FinancialFact[]>, summary?: CompanyResearchSummary | null) {
  const rows = Object.values(factsByFiling).flat();
  const revenue = rows.find((fact) => fact.metric === "Revenues" || fact.metric === "revenue");
  const profit = rows.find((fact) => fact.metric === "NetIncomeLoss" || fact.metric === "net_income");
  if (revenue && profit) return `收入 ${formatCny(revenue.value)}，净利润 ${formatCny(profit.value)}`;
  if (revenue) return `收入 ${formatCny(revenue.value)}`;
  if (profit) return `净利润 ${formatCny(profit.value)}`;
  if (summary?.missing_items?.includes("missing_financial_facts")) return "缺少财务事实";
  return "暂无财务事实";
}

function failureLabel(key: string) {
  const labels: Record<string, string> = {
    missing_annual_report: "年报",
    missing_financial_facts: "财务事实",
    missing_announcements: "公告",
    missing_sentiment: "市场情绪",
    missing_market_fact: "行情热度",
    latest_daily_sync: "最近日更",
  };
  return labels[key] || key;
}

function formatCny(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  const num = Number(value);
  if (Math.abs(num) >= 100000000) return `${(num / 100000000).toFixed(2)}亿`;
  if (Math.abs(num) >= 10000) return `${(num / 10000).toFixed(2)}万`;
  return num.toFixed(2);
}
