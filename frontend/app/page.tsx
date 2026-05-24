"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { colors, shadow, font, card } from "@/lib/styles";

export default function HomePage() {
  const router = useRouter();
  const { workspaces } = useAuth();
  const [health, setHealth] = useState<any>(null);
  const role = workspaces[0]?.role || "user";
  const isAdmin = role === "admin" || role === "owner";

  useEffect(() => {
    api.getHealth().then(setHealth).catch(() => {});
  }, []);

  const navCards = [
    { title: "每日简报", desc: "关注公司、热度企业、异常公告与情绪变化", href: "/finance", icon: briefIcon },
    { title: "公告资产", desc: "年报、公告、图片与索引资产", href: "/documents", icon: docIcon },
    { title: "个性化分析", desc: "公告、财务、热度与情绪的通俗解释", href: "/finance/agent", icon: agentIcon },
    { title: "数据源管理", desc: "CNINFO、AKShare、TuShare 与 MCP 状态", href: "/finance/connectors", icon: sourceIcon, admin: true },
    { title: "评估管理", desc: "A 股公告、财务事实、情绪与简报评估", href: "/finance/evaluations", icon: evalIcon, admin: true },
    { title: "系统设置", desc: "模型、Provider 与运行配置", href: "/settings", icon: settingsIcon, admin: true },
  ].filter((item) => !item.admin || isAdmin);

  return (
    <div>
      <div style={{ textAlign: "center", marginBottom: 32, padding: "32px 0 8px" }}>
        <h1 style={{ fontSize: 32, fontWeight: 800, margin: "0 0 10px", color: colors.text }}>
          A 股公告与情绪分析工作台
        </h1>
        <p style={{ color: colors.textSecondary, fontSize: font.md, margin: 0, lineHeight: 1.6 }}>
          面向 A 股上市公司的公开公告、结构化财务事实、行情热度与市场情绪研究辅助系统。
        </p>
      </div>

      {health && isAdmin && (
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

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 14 }}>
        {navCards.map((item) => (
          <div
            key={item.href}
            onClick={() => router.push(item.href)}
            style={{ ...card, cursor: "pointer", transition: "box-shadow 0.2s, transform 0.15s", padding: 22, marginBottom: 0 }}
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

      <div style={{ marginTop: 36, padding: 20, ...card }}>
        <h3 style={{ margin: "0 0 12px", fontSize: font.sm, fontWeight: 600, color: colors.textSecondary }}>工作流</h3>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: "6px 24px" }}>
          <Version title="数据入口" items={["CNINFO 公告与年报", "AKShare / TuShare 财务与行情", "市场情绪与热度榜"]} />
          <Version title="分析链路" items={["公告索引", "FinancialFact / MarketFact", "SentimentFact", "Verifier 校验"]} />
          <Version title="用户体验" items={["关注列表", "每日站内简报", "异常公告", "个性化研究分析"]} />
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

const briefIcon = <><path d="M4 19h16" /><path d="M4 15h10" /><path d="M4 11h16" /><path d="M4 7h10" /></>;
const docIcon = <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /></>;
const sourceIcon = <><rect x="4" y="4" width="7" height="7" rx="1" /><rect x="13" y="4" width="7" height="7" rx="1" /><rect x="4" y="13" width="7" height="7" rx="1" /><rect x="13" y="13" width="7" height="7" rx="1" /></>;
const agentIcon = <><path d="M12 8V4H8" /><rect x="4" y="8" width="16" height="12" rx="2" /><path d="M9 13h.01" /><path d="M15 13h.01" /><path d="M10 17h4" /></>;
const settingsIcon = <><circle cx="12" cy="12" r="3" /><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2" /></>;
const evalIcon = <><path d="M9 11l3 3L22 4" /><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5" /></>;
