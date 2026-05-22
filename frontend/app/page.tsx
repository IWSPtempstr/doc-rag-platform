"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { colors, radius, shadow, font, card } from "@/lib/styles";

export default function HomePage() {
  const router = useRouter();
  const [health, setHealth] = useState<any>(null);

  useEffect(() => {
    api.getHealth().then(setHealth).catch(() => {});
  }, []);

  const navCards = [
    { title: "财报工作台", desc: "公司、filings、A 股导入、RAG 问答", href: "/finance", icon: financeIcon },
    { title: "数据源工作台", desc: "SEC / CNINFO / AKShare / Chroma 状态", href: "/finance/connectors", icon: sourceIcon },
    { title: "文档资产", desc: "上传、查看、重新索引财报文档", href: "/documents", icon: docIcon },
    { title: "Agent 分析", desc: "证据、事实、计算和校验轨迹", href: "/finance/agent", icon: agentIcon },
    { title: "金融评估", desc: "SEC/FinQA/TAT-QA/custom 数据集评估", href: "/finance/evaluations", icon: evalIcon },
    { title: "设置", desc: "模型与 Provider 配置", href: "/settings", icon: settingsIcon },
    { title: "健康检查", desc: "系统组件状态监控", href: "/health", icon: healthIcon },
  ];

  return (
    <div>
      {/* Hero */}
      <div style={{ textAlign: "center", marginBottom: 32, padding: "32px 0 8px" }}>
        <h1 style={{ fontSize: 32, fontWeight: 800, margin: "0 0 10px", color: colors.text, letterSpacing: "-0.5px" }}>
          财报分析工作台 <span style={{ color: colors.accent }}>v2.1</span>
        </h1>
        <p style={{ color: colors.textSecondary, fontSize: font.md, margin: 0, lineHeight: 1.6 }}>
          SEC 10-K、A 股公告、公共金融 QA 数据集、可追溯 Agent 分析
        </p>
      </div>

      {/* System Status */}
      {health && (
        <div style={{
          ...card, display: "inline-flex", alignItems: "center", gap: 12,
          padding: "10px 20px", marginBottom: 28,
          background: health.status === "ok" ? "#ecfdf5" : "#fffbeb",
          border: `1px solid ${health.status === "ok" ? "#a7f3d0" : "#fcd34d"}`,
        }}>
          <span style={{
            width: 10, height: 10, borderRadius: "50%",
            background: health.status === "ok" ? colors.success : colors.warn,
            display: "inline-block",
          }} />
          <span style={{ fontSize: font.sm, fontWeight: 600, color: colors.text }}>
            系统状态: {health.status}
          </span>
          <span style={{ color: colors.textMuted, fontSize: font.xs }}>
            SQLite: {health.sqlite} · Redis: {health.redis} · Chroma: {health.chroma}
          </span>
        </div>
      )}

      {/* Nav Cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 14 }}>
        {navCards.map((item) => (
          <div
            key={item.href}
            onClick={() => router.push(item.href)}
            style={{
              ...card, cursor: "pointer", transition: "box-shadow 0.2s, transform 0.15s",
              padding: 22, marginBottom: 0,
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.boxShadow = shadow.lg;
              e.currentTarget.style.transform = "translateY(-2px)";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.boxShadow = shadow.sm;
              e.currentTarget.style.transform = "";
            }}
          >
            <div style={{ marginBottom: 10, color: colors.accent }}>
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                {item.icon}
              </svg>
            </div>
            <h3 style={{ margin: "0 0 6px", fontSize: font.md, fontWeight: 600 }}>{item.title}</h3>
            <p style={{ margin: 0, fontSize: font.xs, color: colors.textMuted }}>{item.desc}</p>
          </div>
        ))}
      </div>

      {/* Feature List */}
      <div style={{ marginTop: 36, padding: 20, ...card }}>
        <h3 style={{ margin: "0 0 12px", fontSize: font.sm, fontWeight: 600, color: colors.textSecondary, textTransform: "uppercase", letterSpacing: "0.5px" }}>功能清单</h3>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: "6px 24px" }}>
          <Version title="数据入口" items={["SEC EDGAR 10-K", "CNINFO A 股公告", "本地财报上传", "FinQA / TAT-QA"]} />
          <Version title="分析链路" items={["Chroma 检索", "结构化 FinancialFact", "确定性计算", "Verifier 校验"]} />
          <Version title="工程能力" items={["LangGraph MAS", "MCP 工具", "覆盖报告", "每日 A 股日更"]} />
        </div>
      </div>
    </div>
  );
}

const Version = ({ title, items }: { title: string; items: string[] }) => (
  <div>
    <div style={{ fontSize: font.xs, fontWeight: 700, color: colors.accent, marginBottom: 4, marginTop: 8 }}>{title}</div>
    {items.map((item) => (
      <div key={item} style={{ fontSize: font.xs, color: colors.textSecondary, lineHeight: 1.8 }}>
        {item}
      </div>
    ))}
  </div>
);

const docIcon = <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /><line x1="16" y1="13" x2="8" y2="13" /><line x1="16" y1="17" x2="8" y2="17" /></>;
const financeIcon = <><path d="M3 21h18" /><path d="M5 21V7l8-4 6 4v14" /><path d="M9 21v-6h6v6" /><path d="M9 10h.01" /><path d="M15 10h.01" /></>;
const sourceIcon = <><rect x="4" y="4" width="7" height="7" rx="1" /><rect x="13" y="4" width="7" height="7" rx="1" /><rect x="4" y="13" width="7" height="7" rx="1" /><rect x="13" y="13" width="7" height="7" rx="1" /></>;
const agentIcon = <><path d="M12 8V4H8" /><rect x="4" y="8" width="16" height="12" rx="2" /><path d="M2 14h2" /><path d="M20 14h2" /><path d="M9 13h.01" /><path d="M15 13h.01" /><path d="M10 17h4" /></>;
const settingsIcon = <><circle cx="12" cy="12" r="3" /><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" /></>;
const healthIcon = <><path d="M22 12h-4l-3 9L9 3l-3 9H2" /></>;
const evalIcon = <><path d="M9 11l3 3L22 4" /><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" /></>;
