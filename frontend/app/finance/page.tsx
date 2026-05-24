"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { ProtectedRoute } from "@/lib/auth";
import type { Company, DailyBrief, SentimentFact, WatchlistItem } from "@/lib/types";
import { colors, font, card, btnPrimary, inputBase, btnGhost } from "@/lib/styles";
import { inferAshareMarket, isAshareLikeTicker, normalizeAshareTicker } from "@/lib/ashare";

type FinanceTab = "brief" | "watchlist" | "ingest" | "analysis" | "companies";

export default function FinanceHomePage() {
  return <ProtectedRoute><FinanceHomePageInner /></ProtectedRoute>;
}

function FinanceHomePageInner() {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<FinanceTab>("brief");
  const [companies, setCompanies] = useState<Company[]>([]);
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [brief, setBrief] = useState<DailyBrief | null>(null);
  const [sentiment, setSentiment] = useState<SentimentFact[]>([]);
  const [ticker, setTicker] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [ashareYear, setAshareYear] = useState(String(new Date().getFullYear() - 1));
  const [priority, setPriority] = useState("100");
  const [message, setMessage] = useState("");
  const [announcements, setAnnouncements] = useState<any[]>([]);
  const [question, setQuestion] = useState("");
  const [agentResult, setAgentResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const load = () => {
    api.listCompanies().then((rows: any) => setCompanies(rows)).catch(() => setCompanies([]));
    api.getWatchlist().then((rows: any) => setWatchlist(rows)).catch(() => setWatchlist([]));
    api.getDailyBrief().then((row: any) => setBrief(row)).catch(() => setBrief(null));
    api.getSentimentFacts({ limit: 30 }).then((rows: any) => setSentiment(rows)).catch(() => setSentiment([]));
  };

  useEffect(() => { load(); }, []);

  const addWatch = async () => {
    const symbol = normalizeAshareTicker(ticker);
    if (!isAshareLikeTicker(symbol)) {
      setMessage("请输入 6 位 A 股代码");
      return;
    }
    try {
      await api.addWatchlist({ ticker: symbol, priority: Number(priority) || 100 });
      setMessage(`${symbol} 已加入关注`);
      setTicker("");
      load();
    } catch (err: any) {
      setMessage(`关注失败: ${err.message}`);
    }
  };

  const removeWatch = async (symbol: string) => {
    await api.removeWatchlist(symbol);
    setMessage(`${symbol} 已取消关注`);
    load();
  };

  const createAshareCompany = async () => {
    const symbol = normalizeAshareTicker(ticker);
    if (!isAshareLikeTicker(symbol)) {
      setMessage("请输入 6 位 A 股代码");
      return;
    }
    try {
      await api.createCompany({ ticker: symbol, name: companyName || undefined, exchange: inferAshareMarket(symbol), industry: "A-share" });
      setMessage(`${symbol} 已创建`);
      setTicker("");
      setCompanyName("");
      load();
    } catch (err: any) {
      setMessage(`创建失败: ${err.message}`);
    }
  };

  const searchAnnual = async () => {
    const symbol = normalizeAshareTicker(ticker);
    if (!isAshareLikeTicker(symbol)) {
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

  const importAnnual = async (symbol?: string) => {
    const target = normalizeAshareTicker(symbol || ticker);
    if (!isAshareLikeTicker(target)) {
      setMessage("请输入 6 位 A 股代码");
      return;
    }
    try {
      await api.createCompany({ ticker: target, name: companyName || undefined, exchange: inferAshareMarket(target), industry: "A-share" });
      const filing: any = await api.importAshareFiling(target, { fiscal_year: Number(ashareYear) });
      setMessage(`${target} ${filing.fiscal_year} 年报已加入导入队列`);
      setTicker("");
      setCompanyName("");
      setAnnouncements([]);
      load();
    } catch (err: any) {
      setMessage(`年报导入失败: ${err.message}`);
    }
  };

  const syncMarket = async (symbol: string) => {
    try {
      const result: any = await api.syncAshareMarket(symbol, {});
      setMessage(result.fallback
        ? `${symbol} 暂未取得价格行情，已写入市场热度 ${result.upserted} 条`
        : `${symbol} 行情事实已同步 ${result.upserted} 条`);
      load();
    } catch (err: any) {
      setMessage(`行情同步失败: ${err.message}`);
    }
  };

  const runAnalysis = async () => {
    if (!question.trim()) return;
    const symbol = watchlist[0]?.ticker || companies.find((item) => isAshareLikeTicker(item.ticker))?.ticker;
    if (!symbol) {
      setMessage("请先添加或关注一家 A 股公司");
      return;
    }
    setLoading(true);
    setAgentResult(null);
    try {
      const result: any = await api.queryFinanceAgent({ company_ticker: symbol, question, mode: "full" });
      setAgentResult(result);
    } catch (err: any) {
      setMessage(`分析失败: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const openBriefCompany = async (item: Record<string, any>) => {
    const symbol = normalizeAshareTicker(item.ticker || item.symbol || item["代码"]);
    if (!isAshareLikeTicker(symbol)) {
      setMessage("该简报条目缺少有效 A 股代码");
      return;
    }
    const name = item.name || item["名称"] || symbol;
    try {
      await api.createCompany({
        ticker: symbol,
        name,
        exchange: inferAshareMarket(symbol),
        industry: "A-share",
      });
    } catch (err: any) {
      const text = String(err?.message || "");
      if (!text.includes("exists") && !text.includes("已存在")) {
        setMessage(`创建公司失败: ${text || "未知错误"}`);
        return;
      }
    }
    const params = new URLSearchParams();
    params.set("from", "brief");
    if (brief?.trade_date) params.set("date", brief.trade_date);
    if (item.section) params.set("section", String(item.section));
    if (item.rank) params.set("rank", String(item.rank));
    router.push(`/finance/companies/${symbol}?${params.toString()}`);
  };

  const sentimentSummary = summarizeMarketSentiment(sentiment);

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: font.xxl }}>A 股公告与情绪分析工作台</h1>
          <p style={{ margin: "6px 0 0", color: colors.textSecondary, fontSize: font.sm }}>
            每日站内简报、关注公司、异常公告、行情热度与市场情绪研究辅助。
          </p>
        </div>
        <button style={btnGhost} onClick={() => router.push("/finance/agent")}>打开分析页</button>
      </div>

      {message && (
        <div style={{ ...card, padding: "10px 14px", color: message.includes("失败") ? colors.danger : colors.success }}>
          {message}
        </div>
      )}

      <div style={tabsWrap}>
        <button style={tabButton(activeTab === "brief")} onClick={() => setActiveTab("brief")}>每日简报</button>
        <button style={tabButton(activeTab === "watchlist")} onClick={() => setActiveTab("watchlist")}>关注公司</button>
        <button style={tabButton(activeTab === "ingest")} onClick={() => setActiveTab("ingest")}>公告入口</button>
        <button style={tabButton(activeTab === "analysis")} onClick={() => setActiveTab("analysis")}>个性化分析</button>
        <button style={tabButton(activeTab === "companies")} onClick={() => setActiveTab("companies")}>公司资产</button>
      </div>

      {activeTab === "brief" && (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: 12 }}>
            <Metric title="关注公司" value={String(watchlist.length)} />
            <Metric title="简报条目" value={String(brief?.items?.length ?? 0)} />
            <Metric title="热点补充" value={String(brief?.metadata?.hot_count ?? 0)} />
            <Metric title="情绪事实" value={String(sentiment.length)} />
          </div>

          <div style={card}>
            <h2 style={{ margin: "0 0 8px", fontSize: font.lg }}>今日简报</h2>
            <div style={{ color: colors.textSecondary, fontSize: font.sm, marginBottom: 12 }}>
              {brief?.summary || "暂无简报。添加关注公司或等待日更任务生成。"}
            </div>
            {(brief?.items || []).length === 0 ? (
              <div style={{ color: colors.textMuted, padding: 24, textAlign: "center" }}>暂无条目</div>
            ) : (
              <div style={{ display: "grid", gap: 8 }}>
                {brief!.items.map((item, idx) => {
                  const normalized = normalizeAshareTicker(item.ticker || item.symbol || item["代码"]);
                  return (
                  <button
                    key={`${item.ticker}-${idx}`}
                    onClick={() => openBriefCompany(item)}
                    style={briefItemButton}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                      <strong>{normalized} · {item.name}</strong>
                      <span style={{ color: item.section === "watchlist" ? colors.accent : colors.textMuted, fontSize: font.xs }}>
                        {item.section === "watchlist" ? "关注公司" : `热度 #${item.rank || "-"}`}
                      </span>
                    </div>
                    <div style={{ marginTop: 6, color: colors.textSecondary, fontSize: font.xs }}>
                      {briefReason(item)}
                    </div>
                    <div style={{ marginTop: 8, display: "flex", gap: 6, flexWrap: "wrap" }}>
                      {(item.coverage_tags || inferBriefCoverageTags(item)).map((tagText: string) => (
                        <span key={tagText} style={briefCoverageTag(tagText)}>{tagText}</span>
                      ))}
                    </div>
                  </button>
                )})}
              </div>
            )}
          </div>

          <div style={card}>
            <h2 style={{ margin: "0 0 12px", fontSize: font.lg }}>市场情绪</h2>
            {sentiment.length === 0 ? (
              <div style={{ color: colors.textMuted, fontSize: font.sm }}>暂无情绪事实，可由管理者执行日更任务同步。</div>
            ) : (
              <div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 10 }}>
                  <Metric title="最新交易日" value={sentimentSummary.latest?.trade_date || "-"} />
                  <Metric title="情绪分数" value={formatNumber(sentimentSummary.latest?.score)} />
                  <Metric title="情绪标签" value={sentimentSummary.latest?.label || "unknown"} />
                  <Metric title="较上一条" value={sentimentSummary.delta === null ? "-" : `${sentimentSummary.delta > 0 ? "+" : ""}${formatNumber(sentimentSummary.delta)}`} />
                  <Metric title="30 日均值" value={formatNumber(sentimentSummary.avg)} />
                  <Metric title="最高 / 最低" value={`${formatNumber(sentimentSummary.max)} / ${formatNumber(sentimentSummary.min)}`} />
                </div>
                <div style={{ marginTop: 12, display: "flex", gap: 8, flexWrap: "wrap", color: colors.textSecondary, fontSize: font.xs }}>
                  <span style={tag}>来源：{sentimentSummary.latest?.source || "-"}</span>
                  <span style={tag}>更新时间：{sentimentSummary.latest?.created_at ? new Date(sentimentSummary.latest.created_at).toLocaleString() : "-"}</span>
                </div>
                <div style={{ marginTop: 14, display: "grid", gap: 6 }}>
                  {sentiment.slice(0, 30).map((item) => (
                    <div key={item.id} style={sentimentRow}>
                      <span style={{ width: 90 }}>{item.trade_date}</span>
                      <span style={{ width: 90, color: sentimentColor(item.label) }}>{item.label || "unknown"}</span>
                      <div style={{ flex: 1, height: 8, background: colors.borderLight, borderRadius: 999, overflow: "hidden" }}>
                        <div style={{ width: `${Math.max(0, Math.min(100, Number(item.score || 0)))}%`, height: "100%", background: sentimentColor(item.label) }} />
                      </div>
                      <span style={{ width: 54, textAlign: "right" }}>{formatNumber(item.score)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </>
      )}

      {activeTab === "watchlist" && (
        <div style={card}>
          <h2 style={{ margin: "0 0 12px", fontSize: font.lg }}>关注公司</h2>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 120px auto", gap: 10, marginBottom: 14 }}>
            <input value={ticker} onChange={(e) => setTicker(e.target.value.toUpperCase())} placeholder="600519" style={inputBase} />
            <input value={priority} onChange={(e) => setPriority(e.target.value)} placeholder="优先级" style={inputBase} />
            <button onClick={addWatch} style={btnPrimary}>关注</button>
          </div>
          {watchlist.length === 0 ? (
            <div style={{ color: colors.textMuted, padding: 24, textAlign: "center" }}>未设置关注公司，简报将展示当日热度企业。</div>
          ) : (
            <table style={table}>
              <thead><tr><th style={th}>代码</th><th style={th}>公司</th><th style={th}>优先级</th><th style={th}>操作</th></tr></thead>
              <tbody>
                {watchlist.map((item) => (
                  <tr key={item.id} style={{ borderBottom: `1px solid ${colors.borderLight}` }}>
                    <td style={td}>{item.ticker}</td>
                    <td style={td}>{item.company?.name || item.ticker}</td>
                    <td style={td}>{item.priority}</td>
                    <td style={td}><button style={btnGhost} onClick={() => removeWatch(item.ticker)}>取消关注</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {activeTab === "ingest" && (
        <div style={card}>
          <h2 style={{ margin: "0 0 12px", fontSize: font.lg }}>公告与年报入口</h2>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 10 }}>
            <input value={ticker} onChange={(e) => setTicker(e.target.value.toUpperCase())} placeholder="600519" style={inputBase} />
            <input value={companyName} onChange={(e) => setCompanyName(e.target.value)} placeholder="公司名，可留空" style={inputBase} />
            <input value={ashareYear} onChange={(e) => setAshareYear(e.target.value)} placeholder="年报年份" style={inputBase} />
            <button onClick={createAshareCompany} style={btnPrimary}>添加公司</button>
          </div>
          <div style={{ display: "flex", gap: 8, marginTop: 10, flexWrap: "wrap" }}>
            <button onClick={searchAnnual} style={btnGhost}>搜索年报公告</button>
            <button onClick={() => importAnnual()} style={btnGhost}>添加并导入年报</button>
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

      {activeTab === "analysis" && (
        <div style={card}>
          <h2 style={{ margin: "0 0 12px", fontSize: font.lg }}>个性化研究分析</h2>
          <div style={{ display: "flex", gap: 10 }}>
            <input
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && runAnalysis()}
              placeholder="例如：结合公告、财务事实和情绪变化解释关注公司的今日变化"
              style={{ ...inputBase, flex: 1 }}
            />
            <button onClick={runAnalysis} disabled={loading} style={{ ...btnPrimary, opacity: loading ? 0.6 : 1 }}>
              {loading ? "分析中..." : "分析"}
            </button>
          </div>
          {agentResult && (
            <div style={{ marginTop: 14, borderTop: `1px solid ${colors.borderLight}`, paddingTop: 14 }}>
              <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.7, fontSize: font.sm }}>{agentResult.answer}</div>
            </div>
          )}
        </div>
      )}

      {activeTab === "companies" && (
        <div style={card}>
          <h2 style={{ margin: "0 0 12px", fontSize: font.lg }}>公司资产</h2>
          {companies.length === 0 ? (
            <div style={{ color: colors.textMuted, fontSize: font.sm, padding: 24, textAlign: "center" }}>还没有 A 股公司。</div>
          ) : (
            <table style={table}>
              <thead>
                <tr><th style={th}>代码</th><th style={th}>公司</th><th style={th}>市场</th><th style={th}>公告/年报</th><th style={th}>操作</th></tr>
              </thead>
              <tbody>
                {companies.filter((company) => isAshareLikeTicker(company.ticker)).map((company) => (
                  <tr key={company.id} style={{ borderBottom: `1px solid ${colors.borderLight}` }}>
                    <td style={td}><strong>{company.ticker}</strong></td>
                    <td style={{ ...td, cursor: "pointer", color: colors.accent }} onClick={() => router.push(`/finance/companies/${company.ticker}`)}>{company.name}</td>
                    <td style={td}>{company.exchange || inferAshareMarket(company.ticker)}</td>
                    <td style={td}>{company.filing_count}</td>
                    <td style={td}>
                      <button style={{ ...btnGhost, marginRight: 8 }} onClick={() => importAnnual(company.ticker)}>导入年报</button>
                      <button style={{ ...btnGhost, marginRight: 8 }} onClick={() => syncMarket(company.ticker)}>同步行情</button>
                      <button style={btnGhost} onClick={() => router.push(`/finance/companies/${company.ticker}`)}>详情</button>
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

function briefReason(item: Record<string, any>) {
  const tags = item.coverage_tags || inferBriefCoverageTags(item);
  if (item.section === "watchlist") {
    return tags.includes("缺少基本面验证")
      ? "你已关注这家公司，但公告/财务覆盖不足，优先补全年报和财务事实。"
      : "你已关注这家公司，优先查看它今天的公告、财务和热度变化。";
  }
  const heat = item.heat_score ?? item["热度"] ?? item.value;
  const rank = item.rank || item["排名"];
  if (rank && heat !== undefined && heat !== null) {
    return `今日热度排名 #${rank}，热度值 ${formatNumber(Number(heat))}，先作为市场关注度入口，需结合公告和财务事实验证。`;
  }
  if (rank) return `今日热度排名 #${rank}，适合继续查看公告和财务覆盖情况。`;
  return "可查看公告变化、财务事实、行情热度和市场情绪，不提供买卖建议。";
}

function inferBriefCoverageTags(item: Record<string, any>) {
  const tags: string[] = [];
  if (item.has_announcements || item.announcement_count > 0) tags.push("已有关联公告");
  if (item.has_financial_facts || item.financial_fact_count > 0) tags.push("已有财务事实");
  if (item.heat_score !== undefined && item.heat_score !== null) tags.push("仅热度信号");
  if (!tags.includes("已有财务事实")) tags.push("缺少基本面验证");
  return tags.length ? tags : ["数据覆盖不足"];
}

const table: React.CSSProperties = { width: "100%", borderCollapse: "collapse" };
const th: React.CSSProperties = { textAlign: "left", padding: "10px", fontSize: font.xs, color: colors.textMuted };
const td: React.CSSProperties = { padding: "10px", fontSize: font.sm };
const tag: React.CSSProperties = {
  display: "inline-block",
  padding: "4px 8px",
  borderRadius: 6,
  background: colors.hover,
  border: `1px solid ${colors.borderLight}`,
  fontSize: font.xs,
};

const briefItemButton: React.CSSProperties = {
  display: "block",
  width: "100%",
  textAlign: "left",
  background: colors.surface,
  border: `1px solid ${colors.borderLight}`,
  borderRadius: 8,
  padding: 12,
  cursor: "pointer",
  color: colors.text,
};

const sentimentRow: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 10,
  fontSize: font.xs,
  color: colors.textSecondary,
};
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

function briefCoverageTag(value: string): React.CSSProperties {
  const warning = value.includes("缺少") || value.includes("仅热度") || value.includes("未同步");
  return {
    ...tag,
    background: warning ? "#fffbeb" : colors.hover,
    borderColor: warning ? colors.warn : colors.borderLight,
    color: warning ? "#92400e" : colors.textSecondary,
  };
}

function summarizeMarketSentiment(rows: SentimentFact[]) {
  const scored = rows.filter((item) => item.score !== null && item.score !== undefined);
  const latest = rows[0] || null;
  const previous = rows[1] || null;
  const values = scored.map((item) => Number(item.score));
  const avg = values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
  return {
    latest,
    delta: latest?.score !== null && latest?.score !== undefined && previous?.score !== null && previous?.score !== undefined
      ? Number(latest.score) - Number(previous.score)
      : null,
    avg,
    max: values.length ? Math.max(...values) : null,
    min: values.length ? Math.min(...values) : null,
  };
}

function formatNumber(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return Number(value).toFixed(2);
}

function sentimentColor(label: string | null | undefined) {
  if (label === "positive") return colors.success;
  if (label === "negative") return colors.danger;
  if (label === "neutral") return colors.warn;
  return colors.textMuted;
}
