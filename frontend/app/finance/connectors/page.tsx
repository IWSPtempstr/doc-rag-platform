"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { ProtectedRoute } from "@/lib/auth";
import type { ConnectorStatusResponse, ConnectorStatusRow } from "@/lib/types";
import { colors, font, card, btnGhost } from "@/lib/styles";

export default function FinanceConnectorsPage() {
  return <ProtectedRoute><FinanceConnectorsInner /></ProtectedRoute>;
}

function FinanceConnectorsInner() {
  const [status, setStatus] = useState<ConnectorStatusResponse | null>(null);
  const [message, setMessage] = useState("");
  const [testing, setTesting] = useState<Record<string, boolean>>({});

  const load = () => {
    api.getConnectorStatus()
      .then((data: any) => setStatus(data))
      .catch((err: any) => setMessage(`加载失败: ${err.message}`));
  };

  useEffect(() => { load(); }, []);

  const testConnector = async (name: string) => {
    setTesting((prev) => ({ ...prev, [name]: true }));
    setMessage("");
    try {
      const result: any = await api.testConnector(name);
      setStatus((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          connectors: prev.connectors.map((row) => row.name === name ? { ...row, ...result } : row),
        };
      });
      setMessage(`${result.label || name}: ${result.status}`);
    } catch (err: any) {
      setMessage(`测试失败: ${err.message}`);
    } finally {
      setTesting((prev) => ({ ...prev, [name]: false }));
    }
  };

  const connectors = status?.connectors || [];

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: font.xxl }}>数据源 / Connector 工作台</h1>
          <p style={{ margin: "6px 0 0", color: colors.textSecondary, fontSize: font.sm }}>
            管理 SEC、CNINFO、AKShare、公开评测集与 Chroma 索引覆盖。
          </p>
        </div>
        <button onClick={load} style={btnGhost}>刷新</button>
      </div>

      {message && (
        <div style={{ ...card, padding: "10px 14px", color: message.includes("失败") ? colors.danger : colors.success }}>
          {message}
        </div>
      )}

      <div style={card}>
        <h2 style={{ margin: "0 0 12px", fontSize: font.lg }}>连接状态</h2>
        {connectors.length === 0 ? (
          <div style={{ color: colors.textMuted, padding: 24, textAlign: "center" }}>暂无 connector 状态</div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ borderBottom: `1px solid ${colors.border}` }}>
                  <th style={th}>数据源</th>
                  <th style={th}>类型</th>
                  <th style={th}>状态</th>
                  <th style={th}>覆盖</th>
                  <th style={th}>最近同步</th>
                  <th style={th}>失败原因</th>
                  <th style={th}>操作</th>
                </tr>
              </thead>
              <tbody>
                {connectors.map((row) => (
                  <tr key={row.name} style={{ borderBottom: `1px solid ${colors.borderLight}` }}>
                    <td style={td}>
                      <strong>{row.label}</strong>
                      <div style={{ color: colors.textMuted, fontSize: font.xs, marginTop: 3, wordBreak: "break-word" }}>
                        {row.source}
                      </div>
                      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 6 }}>
                        {row.capabilities.slice(0, 3).map((cap) => (
                          <span key={cap} style={pill}>{cap}</span>
                        ))}
                      </div>
                    </td>
                    <td style={td}>{row.category}</td>
                    <td style={td}>
                      <span style={statusBadge(row.status)}>{row.status}</span>
                    </td>
                    <td style={td}>
                      <Coverage coverage={row.coverage} />
                    </td>
                    <td style={td}>{formatDate(row.last_sync_at)}</td>
                    <td style={{ ...td, color: row.failure_reason ? colors.danger : colors.textMuted }}>
                      {row.failure_reason || "-"}
                    </td>
                    <td style={td}>
                      <button
                        onClick={() => testConnector(row.name)}
                        disabled={!!testing[row.name]}
                        style={{ ...btnGhost, opacity: testing[row.name] ? 0.6 : 1 }}
                      >
                        {testing[row.name] ? "测试中..." : "测试"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div style={card}>
        <h2 style={{ margin: "0 0 12px", fontSize: font.lg }}>定时更新任务</h2>
        {(status?.daily_jobs || []).map((job) => (
          <div key={job.name} style={{ border: `1px solid ${colors.borderLight}`, borderRadius: 8, padding: 14, marginBottom: 10 }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
              <div>
                <strong>{job.name}</strong>
                <div style={{ color: colors.textSecondary, fontSize: font.xs, marginTop: 4 }}>
                  {job.source} · {job.schedule}
                </div>
              </div>
              <span style={statusBadge(job.status)}>{job.status}</span>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 8, marginTop: 12 }}>
              <Mini label="上次运行" value={formatDate(job.last_run_at)} />
              <Mini label="下次运行" value={formatDate(job.next_run_at)} />
              <Mini label="失败原因" value={job.failure_reason || "-"} danger={!!job.failure_reason} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Coverage({ coverage }: { coverage: ConnectorStatusRow["coverage"] }) {
  const entries = Object.entries(coverage || {});
  if (entries.length === 0) return <span style={{ color: colors.textMuted }}>-</span>;
  return (
    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
      {entries.map(([key, value]) => (
        <span key={key} style={pill}>{key}: {String(value ?? "-")}</span>
      ))}
    </div>
  );
}

function Mini({ label, value, danger }: { label: string; value: string; danger?: boolean }) {
  return (
    <div style={{ background: colors.hover, borderRadius: 6, padding: "8px 10px" }}>
      <div style={{ color: colors.textMuted, fontSize: font.xs }}>{label}</div>
      <div style={{ color: danger ? colors.danger : colors.text, fontSize: font.sm, marginTop: 3 }}>{value}</div>
    </div>
  );
}

function formatDate(value: string | null | undefined) {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
}

function statusBadge(status: string): React.CSSProperties {
  const color = status === "available" || status === "configured" || status === "success"
    ? colors.success
    : status === "unavailable" || status === "failed"
      ? colors.danger
      : colors.warn;
  return {
    display: "inline-block",
    padding: "3px 8px",
    borderRadius: 6,
    fontSize: font.xs,
    fontWeight: 700,
    color: "#fff",
    background: color,
  };
}

const th: React.CSSProperties = { textAlign: "left", padding: "10px", fontSize: font.xs, color: colors.textMuted, fontWeight: 600 };
const td: React.CSSProperties = { padding: "12px 10px", fontSize: font.sm, verticalAlign: "top" };
const pill: React.CSSProperties = {
  display: "inline-block",
  padding: "2px 7px",
  borderRadius: 6,
  background: colors.hover,
  color: colors.textSecondary,
  fontSize: font.xs,
};
