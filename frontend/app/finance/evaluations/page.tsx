"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { ProtectedRoute } from "@/lib/auth";
import type { EvalCase, EvalDataset, FinanceEvalResult } from "@/lib/types";
import { colors, font, card, btnPrimary, btnGhost, btnDanger, inputBase } from "@/lib/styles";

export default function FinanceEvaluationsPage() {
  return <ProtectedRoute><FinanceEvaluationsPageInner /></ProtectedRoute>;
}

function FinanceEvaluationsPageInner() {
  const [tab, setTab] = useState<"eval" | "datasets">("eval");
  const [dataset, setDataset] = useState("custom_10k");
  const [running, setRunning] = useState(false);
  const [results, setResults] = useState<FinanceEvalResult[]>([]);
  const [message, setMessage] = useState("");

  // Datasets state
  const [datasets, setDatasets] = useState<EvalDataset[]>([]);
  const [cases, setCases] = useState<EvalCase[]>([]);
  const [selectedDs, setSelectedDs] = useState<number | null>(null);
  const [caseFilter, setCaseFilter] = useState("");
  const [dsLoading, setDsLoading] = useState(false);

  const loadEval = () => api.listFinanceEvaluationResults().then((rows: any) => setResults(rows)).catch(() => setResults([]));
  const loadDatasets = () => { api.listDatasets().then((rows: any) => setDatasets(rows)).catch(() => {}); };

  useEffect(() => { loadEval(); loadDatasets(); }, []);

  const loadCases = (dsId: number, statusFilter?: string) => {
    setSelectedDs(dsId);
    const s = statusFilter !== undefined ? statusFilter : caseFilter;
    api.getDatasetCases(dsId, s || undefined).then((rows: any) => setCases(rows)).catch(() => setCases([]));
  };

  const runEval = async () => {
    setRunning(true);
    setMessage("");
    try {
      await api.runFinanceEvaluation({ dataset_source: dataset, strategy: "finance_agent" });
      setMessage("评估完成");
      loadEval();
    } catch (err: any) {
      setMessage(`评估失败: ${err.message}`);
    } finally {
      setRunning(false);
    }
  };

  const buildDataset = async (action: string) => {
    setDsLoading(true);
    setMessage("");
    try {
      if (action === "sec") await api.buildSec10kDataset({});
      else if (action === "fb") await api.importFinancebenchDataset();
      else if (action === "finqa") await api.importFinqaDataset({ subset: "train", limit: 25 });
      else if (action === "tatqa") await api.importTatqaDataset({ subset: "train", limit: 25 });
      else if (action === "custom") await api.buildCustom10kDataset();
      setMessage(`${action} 构建完成`);
      loadDatasets();
    } catch (err: any) {
      setMessage(`${action} 失败: ${err.message}`);
    } finally {
      setDsLoading(false);
    }
  };

  const updateCase = async (caseId: number, status: string) => {
    await api.updateEvalCase(caseId, { status });
    if (selectedDs) loadCases(selectedDs);
  };

  const freeze = async (dsId: number) => {
    await api.freezeDataset(dsId);
    loadDatasets();
  };

  const tabStyle = (t: string): React.CSSProperties => ({
    padding: "8px 20px",
    border: "none",
    background: tab === t ? colors.accent : colors.hover,
    color: tab === t ? "#fff" : colors.textSecondary,
    borderRadius: 6,
    cursor: "pointer",
    fontSize: font.sm,
    fontWeight: 600,
  });

  return (
    <div>
      <h1 style={{ margin: "0 0 6px", fontSize: font.xxl }}>金融评估</h1>
      <p style={{ margin: "0 0 20px", color: colors.textSecondary, fontSize: font.sm }}>
        FinQA/TAT-QA 风格数据集 + 自建 10-K 任务评估 RAG + Agent。
      </p>

      <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
        <button style={tabStyle("eval")} onClick={() => setTab("eval")}>运行评估</button>
        <button style={tabStyle("datasets")} onClick={() => setTab("datasets")}>数据集管理</button>
      </div>

      {message && (
        <div style={{ ...card, padding: "10px 14px", color: message.includes("失败") ? colors.danger : colors.success, marginBottom: 16 }}>
          {message}
        </div>
      )}

      {tab === "eval" && (
        <>
          <div style={card}>
            <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
              <select value={dataset} onChange={(e) => setDataset(e.target.value)} style={{ ...inputBase, minWidth: 180 }}>
                <option value="custom_10k">Custom 10-K</option>
                <option value="sec_10k">SEC 10-K</option>
                <option value="finqa">FinQA</option>
                <option value="tatqa">TAT-QA</option>
                <option value="financebench_sample_all">FinanceBench</option>
              </select>
              <button onClick={runEval} disabled={running} style={{ ...btnPrimary, opacity: running ? 0.6 : 1 }}>
                {running ? "运行中..." : "运行评估"}
              </button>
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
                  {Object.entries(result.metrics || {})
                    .filter(([, value]) => value === null || typeof value !== "object" || Array.isArray(value))
                    .map(([key, value]) => (
                      <div key={key} style={{ background: colors.hover, borderRadius: 6, padding: "8px 10px" }}>
                        <div style={{ color: colors.textMuted, fontSize: font.xs }}>{key}</div>
                        <div style={{ fontWeight: 700 }}>{renderMetricValue(value)}</div>
                      </div>
                    ))}
                </div>
                {result.results?.length ? (
                  <div style={{ marginTop: 12, background: colors.hover, borderRadius: 6, padding: 10 }}>
                    <div style={{ color: colors.textSecondary, fontSize: font.sm, fontWeight: 700, marginBottom: 6 }}>failure_type</div>
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                      {Object.entries(groupFailures(result.results)).map(([key, value]) => (
                        <span key={key} style={{ fontSize: font.xs, color: colors.textSecondary }}>
                          {key}: {String(value)}
                        </span>
                      ))}
                    </div>
                  </div>
                ) : null}
                {result.metrics?.by_task_type && (
                  <div style={{ marginTop: 12 }}>
                    <div style={{ color: colors.textSecondary, fontSize: font.sm, fontWeight: 700, marginBottom: 8 }}>by_task_type</div>
                    <div style={{ overflowX: "auto" }}>
                      <table style={{ width: "100%", borderCollapse: "collapse" }}>
                        <thead>
                          <tr style={{ borderBottom: `1px solid ${colors.border}` }}>
                            <th style={th}>task_type</th>
                            <th style={th}>total</th>
                            <th style={th}>retrieval_hit_rate</th>
                            <th style={th}>numeric_accuracy</th>
                            <th style={th}>evidence_recall</th>
                            <th style={th}>fact_grounding_rate</th>
                            <th style={th}>abstain_accuracy</th>
                          </tr>
                        </thead>
                        <tbody>
                          {Object.entries(result.metrics.by_task_type).map(([taskType, stats]: [string, any]) => (
                            <tr key={taskType} style={{ borderBottom: `1px solid ${colors.borderLight}` }}>
                              <td style={td}>{taskType}</td>
                              <td style={td}>{stats.total ?? "-"}</td>
                              <td style={td}>{renderMetricValue(stats.retrieval_hit_rate)}</td>
                              <td style={td}>{renderMetricValue(stats.numeric_accuracy)}</td>
                              <td style={td}>{renderMetricValue(stats.evidence_recall)}</td>
                              <td style={td}>{renderMetricValue(stats.fact_grounding_rate)}</td>
                              <td style={td}>{renderMetricValue(stats.abstain_accuracy)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </>
      )}

      {tab === "datasets" && (
        <>
          <div style={card}>
            <h2 style={{ margin: "0 0 12px", fontSize: font.lg }}>构建数据集</h2>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              <button onClick={() => buildDataset("sec")} disabled={dsLoading} style={btnPrimary}>
                {dsLoading ? "构建中..." : "构建 SEC 10-K 数据集"}
              </button>
              <button onClick={() => buildDataset("fb")} disabled={dsLoading} style={btnPrimary}>
                导入 FinanceBench Sample
              </button>
              <button onClick={() => buildDataset("finqa")} disabled={dsLoading} style={btnPrimary}>
                导入 FinQA Sample
              </button>
              <button onClick={() => buildDataset("tatqa")} disabled={dsLoading} style={btnPrimary}>
                导入 TAT-QA Sample
              </button>
              <button onClick={() => buildDataset("custom")} disabled={dsLoading} style={btnGhost}>
                生成自建 10-K Cases
              </button>
            </div>
          </div>

          <div style={card}>
            <h2 style={{ margin: "0 0 12px", fontSize: font.lg }}>数据集列表</h2>
            {datasets.length === 0 ? (
              <div style={{ color: colors.textMuted, padding: 24, textAlign: "center" }}>暂无数据集，点击上方按钮构建</div>
            ) : (
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ borderBottom: `1px solid ${colors.border}` }}>
                    <th style={th}>名称</th>
                    <th style={th}>来源</th>
                    <th style={th}>版本</th>
                    <th style={th}>Cases</th>
                    <th style={th}>状态</th>
                    <th style={th}>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {datasets.map((ds) => (
                    <tr key={ds.id} style={{ borderBottom: `1px solid ${colors.borderLight}` }}>
                      <td style={td}>
                        <a onClick={() => loadCases(ds.id)} style={{ color: colors.accent, cursor: "pointer", fontWeight: 600 }}>
                          {ds.name}
                        </a>
                        {ds.description && <div style={{ color: colors.textMuted, fontSize: font.xs }}>{ds.description}</div>}
                      </td>
                      <td style={td}>{ds.source}</td>
                      <td style={td}>{ds.version}</td>
                      <td style={td}>{ds.case_count}</td>
                      <td style={td}>
                        {ds.frozen_at
                          ? <span style={{ color: colors.success, fontWeight: 600 }}>Frozen</span>
                          : <span style={{ color: colors.textMuted }}>Active</span>
                        }
                        {ds.license_note && <div style={{ color: colors.textMuted, fontSize: font.xs }}>{ds.license_note}</div>}
                        {ds.source_url && <div style={{ color: colors.textMuted, fontSize: font.xs, wordBreak: "break-word" }}>{ds.source_url}</div>}
                      </td>
                      <td style={td}>
                        <button onClick={() => loadCases(ds.id)} style={{ ...btnGhost, marginRight: 6 }}>查看</button>
                        {!ds.frozen_at && (
                          <button onClick={() => freeze(ds.id)} style={{ ...btnGhost, color: colors.warn }}>冻结</button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {selectedDs && (
            <div style={card}>
              <h2 style={{ margin: "0 0 10px", fontSize: font.lg }}>Cases · Dataset #{selectedDs}</h2>
              <div style={{ display: "flex", gap: 8, marginBottom: 14 }}>
                <select value={caseFilter} onChange={(e) => { const v = e.target.value; setCaseFilter(v); if (selectedDs) loadCases(selectedDs, v); }}
                  style={{ ...inputBase, minWidth: 130 }}>
                  <option value="">全部状态</option>
                  <option value="draft">Draft</option>
                  <option value="approved">Approved</option>
                  <option value="rejected">Rejected</option>
                </select>
              </div>
              {cases.length === 0 ? (
                <div style={{ color: colors.textMuted, padding: 24, textAlign: "center" }}>暂无用例</div>
              ) : cases.map((c) => (
                <div key={c.id} style={{ border: `1px solid ${colors.borderLight}`, borderRadius: 8, padding: 12, marginBottom: 8 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 12, marginBottom: 6 }}>
                    <div style={{ flex: 1 }}>
                      <strong style={{ fontSize: font.sm }}>{c.question}</strong>
                      <div style={{ color: colors.textMuted, fontSize: font.xs, marginTop: 4 }}>
                        {c.task_type} · {c.difficulty} · {c.status}
                        {c.metadata_json?.ticker && <> · {c.metadata_json.ticker} FY{c.metadata_json.fiscal_year}</>}
                      </div>
                    </div>
                    <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
                      {c.status !== "approved" && (
                        <button onClick={() => updateCase(c.id, "approved")} style={{ ...btnPrimary, padding: "4px 12px", fontSize: font.xs }}>
                          Approve
                        </button>
                      )}
                      {c.status !== "rejected" && (
                        <button onClick={() => updateCase(c.id, "rejected")} style={{ ...btnDanger, padding: "4px 12px", fontSize: font.xs }}>
                          Reject
                        </button>
                      )}
                    </div>
                  </div>
                  {c.expected_answer && (
                    <div style={{ background: colors.hover, borderRadius: 6, padding: "8px 10px", fontSize: font.xs, color: colors.textSecondary }}>
                      Gold: {c.expected_answer.slice(0, 200)}
                      {c.expected_numeric != null && <span> ({c.expected_numeric})</span>}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

const th: React.CSSProperties = { textAlign: "left", padding: "10px", fontSize: font.xs, color: colors.textMuted, fontWeight: 600 };
const td: React.CSSProperties = { padding: "10px", fontSize: font.sm };

function renderMetricValue(value: any) {
  if (value === null || value === undefined) return "-";
  if (typeof value === "number") return value.toFixed(4);
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}

function groupFailures(results: any[]) {
  return results.reduce((acc: Record<string, number>, item) => {
    const key = item.failure_type || (item.skipped ? "skipped" : "ok");
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
}
