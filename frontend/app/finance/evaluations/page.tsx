"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { ProtectedRoute } from "@/lib/auth";
import type { EvalCase, EvalDataset, FinanceAlert, FinanceEvalJsonlExport, FinanceEvalResult, FinanceSummary } from "@/lib/types";
import { colors, font, card, btnPrimary, btnGhost, btnDanger, inputBase } from "@/lib/styles";

export default function FinanceEvaluationsPage() {
  return <ProtectedRoute><FinanceEvaluationsPageInner /></ProtectedRoute>;
}

function FinanceEvaluationsPageInner() {
  const [tab, setTab] = useState<"eval" | "datasets">("eval");
  const [dataset, setDataset] = useState("ashare_daily_brief");
  const [running, setRunning] = useState(false);
  const [results, setResults] = useState<FinanceEvalResult[]>([]);
  const [alerts, setAlerts] = useState<FinanceAlert[]>([]);
  const [message, setMessage] = useState("");
  const [datasets, setDatasets] = useState<EvalDataset[]>([]);
  const [summary, setSummary] = useState<FinanceSummary | null>(null);
  const [cases, setCases] = useState<EvalCase[]>([]);
  const [selectedDs, setSelectedDs] = useState<number | null>(null);
  const [caseFilter, setCaseFilter] = useState("");
  const [dsLoading, setDsLoading] = useState(false);
  const [jsonlDataset, setJsonlDataset] = useState("ashare_daily_brief");
  const [jsonlPath, setJsonlPath] = useState("/home/work/worktowork/data/evaluations/finance_agent/ashare_daily_brief.jsonl");

  const loadEval = () => api.listFinanceEvaluationResults().then((rows: any) => setResults(rows)).catch(() => setResults([]));
  const loadAlerts = () => api.getFinanceAlerts(20).then((rows: any) => setAlerts(rows)).catch(() => setAlerts([]));
  const loadDatasets = () => {
    api.listDatasets().then((rows: any) => setDatasets(rows)).catch(() => {});
    api.getFinanceSummary().then((row: any) => setSummary(row)).catch(() => setSummary(null));
  };

  useEffect(() => { loadEval(); loadAlerts(); loadDatasets(); }, []);

  const runEval = async () => {
    setRunning(true);
    setMessage("");
    try {
      await api.runFinanceEvaluation({ dataset_source: dataset, strategy: "ashare_agent" });
      setMessage("评估完成");
      loadEval();
      loadAlerts();
    } catch (err: any) {
      setMessage(`评估失败: ${err.message}`);
    } finally {
      setRunning(false);
    }
  };

  const loadCases = (dsId: number, statusFilter?: string) => {
    setSelectedDs(dsId);
    const s = statusFilter !== undefined ? statusFilter : caseFilter;
    api.getDatasetCases(dsId, s || undefined).then((rows: any) => setCases(rows)).catch(() => setCases([]));
  };

  const updateCase = async (caseId: number, status: string) => {
    await api.updateEvalCase(caseId, { status });
    if (selectedDs) loadCases(selectedDs);
  };

  const freeze = async (dsId: number) => {
    await api.freezeDataset(dsId);
    loadDatasets();
  };

  const importJsonl = async () => {
    setDsLoading(true);
    setMessage("");
    try {
      const res: any = await api.importFinanceEvalJsonl({ dataset_name: jsonlDataset, file_path: jsonlPath });
      setMessage(`JSONL 导入完成: ${res.case_count} cases`);
      loadDatasets();
    } catch (err: any) {
      setMessage(`JSONL 导入失败: ${err.message}`);
    } finally {
      setDsLoading(false);
    }
  };

  const exportJsonl = async () => {
    setDsLoading(true);
    setMessage("");
    try {
      const res = (await api.exportFinanceEvalJsonl(jsonlDataset)) as FinanceEvalJsonlExport;
      setJsonlPath(res.file_path);
      setMessage(`JSONL 已导出: ${res.file_path}`);
    } catch (err: any) {
      setMessage(`JSONL 导出失败: ${err.message}`);
    } finally {
      setDsLoading(false);
    }
  };

  return (
    <div>
      <h1 style={{ margin: "0 0 6px", fontSize: font.xxl }}>A 股专项评估</h1>
      <p style={{ margin: "0 0 20px", color: colors.textSecondary, fontSize: font.sm }}>
        评估公告检索、财务事实、行情事实、市场情绪、每日简报与 Agent 轨迹。
      </p>

      <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
        <button style={tabStyle(tab === "eval")} onClick={() => setTab("eval")}>运行评估</button>
        <button style={tabStyle(tab === "datasets")} onClick={() => setTab("datasets")}>数据集管理</button>
      </div>

      {message && (
        <div style={{ ...card, padding: "10px 14px", color: message.includes("失败") ? colors.danger : colors.success, marginBottom: 16 }}>
          {message}
        </div>
      )}

      <div style={card}>
        <h2 style={{ margin: "0 0 12px", fontSize: font.lg }}>A 股评估概览</h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 10 }}>
          {buildSourceRows(datasets).map((row) => (
            <div key={row.label} style={{ background: colors.hover, borderRadius: 6, padding: "10px 12px" }}>
              <div style={{ color: colors.textMuted, fontSize: font.xs }}>{row.label}</div>
              <div style={{ fontSize: font.lg, fontWeight: 700, marginTop: 4 }}>{row.cases}</div>
              <div style={{ color: colors.textSecondary, fontSize: font.xs, marginTop: 3 }}>
                datasets {row.datasets} · frozen {row.frozen}
              </div>
            </div>
          ))}
        </div>
        {summary && Object.keys(summary.dataset_failure_counts || {}).length > 0 && (
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12 }}>
            {Object.entries(summary.dataset_failure_counts).map(([reason, count]) => (
              <span key={reason} style={{ ...tag, color: colors.warn }}>{reason}: {count}</span>
            ))}
          </div>
        )}
      </div>

      {alerts.length > 0 && (
        <div style={card}>
          <h2 style={{ margin: "0 0 12px", fontSize: font.lg }}>Observability Alerts</h2>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {alerts.slice(0, 8).map((alert, idx) => (
              <span key={`${alert.created_at}-${idx}`} style={{ ...tag, color: alert.severity === "critical" ? colors.danger : colors.warn }}>
                {alert.alert_type}: {renderMetricValue(alert.metric_value)}
              </span>
            ))}
          </div>
        </div>
      )}

      {tab === "eval" && (
        <>
          <div style={card}>
            <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
              <select value={dataset} onChange={(e) => setDataset(e.target.value)} style={{ ...inputBase, minWidth: 220 }}>
                <option value="ashare_daily_brief">A 股每日简报</option>
                <option value="ashare_announcement">A 股公告检索</option>
                <option value="ashare_financial_fact">A 股财务事实</option>
                <option value="ashare_market_sentiment">A 股市场情绪</option>
              </select>
              <button onClick={runEval} disabled={running} style={{ ...btnPrimary, opacity: running ? 0.6 : 1 }}>
                {running ? "运行中..." : "运行评估"}
              </button>
            </div>
          </div>

          <ResultList results={results} />
        </>
      )}

      {tab === "datasets" && (
        <>
          <div style={card}>
            <h2 style={{ margin: "0 0 12px", fontSize: font.lg }}>A 股 JSONL 数据集</h2>
            <div style={{ display: "grid", gridTemplateColumns: "minmax(160px, 220px) 1fr auto auto", gap: 10, alignItems: "center" }}>
              <input value={jsonlDataset} onChange={(e) => setJsonlDataset(e.target.value)} style={inputBase} />
              <input value={jsonlPath} onChange={(e) => setJsonlPath(e.target.value)} style={inputBase} />
              <button onClick={importJsonl} disabled={dsLoading} style={btnPrimary}>导入 JSONL</button>
              <button onClick={exportJsonl} disabled={dsLoading} style={btnGhost}>导出 JSONL</button>
            </div>
          </div>

          <DatasetList
            datasets={datasets}
            selectedDs={selectedDs}
            cases={cases}
            caseFilter={caseFilter}
            onLoadCases={loadCases}
            onFilter={setCaseFilter}
            onFreeze={freeze}
            onUpdateCase={updateCase}
          />
        </>
      )}
    </div>
  );
}

function ResultList({ results }: { results: FinanceEvalResult[] }) {
  return (
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
            {Object.entries(result.metrics || {})
              .filter(([, value]) => value === null || typeof value !== "object" || Array.isArray(value))
              .map(([key, value]) => (
                <div key={key} style={{ background: colors.hover, borderRadius: 6, padding: "8px 10px" }}>
                  <div style={{ color: colors.textMuted, fontSize: font.xs }}>{key}</div>
                  <div style={{ fontWeight: 700 }}>{renderMetricValue(value)}</div>
                </div>
              ))}
          </div>
          {result.metrics?.efficiency && (
            <div style={{ marginTop: 12, background: colors.hover, borderRadius: 6, padding: 10 }}>
              {Object.entries(result.metrics.efficiency).map(([key, value]) => (
                <span key={key} style={{ fontSize: font.xs, color: colors.textSecondary, marginRight: 10 }}>
                  {key}: {renderMetricValue(value)}
                </span>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function DatasetList(props: {
  datasets: EvalDataset[];
  selectedDs: number | null;
  cases: EvalCase[];
  caseFilter: string;
  onLoadCases: (id: number, status?: string) => void;
  onFilter: (value: string) => void;
  onFreeze: (id: number) => void;
  onUpdateCase: (id: number, status: string) => void;
}) {
  return (
    <>
      <div style={card}>
        <h2 style={{ margin: "0 0 12px", fontSize: font.lg }}>数据集列表</h2>
        {props.datasets.length === 0 ? (
          <div style={{ color: colors.textMuted, padding: 24, textAlign: "center" }}>暂无数据集，可通过 JSONL 导入</div>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: `1px solid ${colors.border}` }}>
                <th style={th}>名称</th><th style={th}>来源</th><th style={th}>版本</th><th style={th}>Cases</th><th style={th}>状态</th><th style={th}>操作</th>
              </tr>
            </thead>
            <tbody>
              {props.datasets.map((ds) => (
                <tr key={ds.id} style={{ borderBottom: `1px solid ${colors.borderLight}` }}>
                  <td style={td}><a onClick={() => props.onLoadCases(ds.id)} style={{ color: colors.accent, cursor: "pointer", fontWeight: 600 }}>{ds.name}</a></td>
                  <td style={td}>{ds.source}</td>
                  <td style={td}>{ds.version}</td>
                  <td style={td}>{ds.case_count}</td>
                  <td style={td}>{ds.frozen_at ? <span style={{ color: colors.success }}>Frozen</span> : <span style={{ color: colors.textMuted }}>Active</span>}</td>
                  <td style={td}>
                    <button onClick={() => props.onLoadCases(ds.id)} style={{ ...btnGhost, marginRight: 6 }}>查看</button>
                    {!ds.frozen_at && <button onClick={() => props.onFreeze(ds.id)} style={{ ...btnGhost, color: colors.warn }}>冻结</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {props.selectedDs && (
        <div style={card}>
          <h2 style={{ margin: "0 0 10px", fontSize: font.lg }}>Cases · Dataset #{props.selectedDs}</h2>
          <select value={props.caseFilter} onChange={(e) => { props.onFilter(e.target.value); props.onLoadCases(props.selectedDs!, e.target.value); }} style={{ ...inputBase, minWidth: 130, marginBottom: 14 }}>
            <option value="">全部状态</option><option value="draft">Draft</option><option value="approved">Approved</option><option value="rejected">Rejected</option>
          </select>
          {props.cases.map((c) => (
            <div key={c.id} style={{ border: `1px solid ${colors.borderLight}`, borderRadius: 8, padding: 12, marginBottom: 8 }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                <div><strong style={{ fontSize: font.sm }}>{c.question}</strong><div style={{ color: colors.textMuted, fontSize: font.xs, marginTop: 4 }}>{c.task_type} · {c.difficulty} · {c.status}</div></div>
                <div style={{ display: "flex", gap: 6 }}>
                  {c.status !== "approved" && <button onClick={() => props.onUpdateCase(c.id, "approved")} style={{ ...btnPrimary, padding: "4px 12px", fontSize: font.xs }}>Approve</button>}
                  {c.status !== "rejected" && <button onClick={() => props.onUpdateCase(c.id, "rejected")} style={{ ...btnDanger, padding: "4px 12px", fontSize: font.xs }}>Reject</button>}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  );
}

const th: React.CSSProperties = { textAlign: "left", padding: "10px", fontSize: font.xs, color: colors.textMuted, fontWeight: 600 };
const td: React.CSSProperties = { padding: "10px", fontSize: font.sm };
const tag: React.CSSProperties = { display: "inline-block", padding: "3px 8px", borderRadius: 6, background: colors.hover, border: `1px solid ${colors.borderLight}`, fontSize: font.xs };

function tabStyle(active: boolean): React.CSSProperties {
  return { padding: "8px 20px", border: "none", background: active ? colors.accent : colors.hover, color: active ? "#fff" : colors.textSecondary, borderRadius: 6, cursor: "pointer", fontSize: font.sm, fontWeight: 600 };
}

function renderMetricValue(value: any) {
  if (value === null || value === undefined) return "-";
  if (typeof value === "number") return value.toFixed(4);
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}

function buildSourceRows(datasets: EvalDataset[]) {
  const buckets: Record<string, { label: string; datasets: number; cases: number; frozen: number }> = {
    announcement: { label: "公告检索", datasets: 0, cases: 0, frozen: 0 },
    facts: { label: "财务/行情事实", datasets: 0, cases: 0, frozen: 0 },
    sentiment: { label: "市场情绪", datasets: 0, cases: 0, frozen: 0 },
    brief: { label: "每日简报", datasets: 0, cases: 0, frozen: 0 },
  };
  datasets.forEach((ds) => {
    const name = `${ds.name} ${ds.source}`.toLowerCase();
    const key = name.includes("sentiment") || name.includes("情绪") ? "sentiment" :
      name.includes("brief") || name.includes("简报") ? "brief" :
      name.includes("fact") || name.includes("事实") ? "facts" : "announcement";
    buckets[key].datasets += 1;
    buckets[key].cases += ds.case_count || 0;
    if (ds.frozen_at) buckets[key].frozen += 1;
  });
  return Object.values(buckets);
}
