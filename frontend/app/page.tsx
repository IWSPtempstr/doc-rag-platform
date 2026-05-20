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
    { title: "文档管理", desc: "上传、查看、管理文档", href: "/documents", icon: docIcon },
    { title: "问答", desc: "RAG 智能问答 + 缓存", href: "/chat", icon: chatIcon },
    { title: "设置", desc: "模型与 Provider 配置", href: "/settings", icon: settingsIcon },
    { title: "健康检查", desc: "系统组件状态监控", href: "/health", icon: healthIcon },
    { title: "评估", desc: "Golden Questions 评估", href: "/evaluations", icon: evalIcon },
  ];

  return (
    <div>
      {/* Hero */}
      <div style={{ textAlign: "center", marginBottom: 32, padding: "32px 0 8px" }}>
        <h1 style={{ fontSize: 32, fontWeight: 800, margin: "0 0 10px", color: colors.text, letterSpacing: "-0.5px" }}>
          文档 RAG 平台 <span style={{ color: colors.accent }}>v2.0</span>
        </h1>
        <p style={{ color: colors.textSecondary, fontSize: font.md, margin: 0, lineHeight: 1.6 }}>
          上传文档，多模态解析，智能问答，可追溯评估
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
          <Version title="v1" items={["文档上传/管理", "任务状态追踪", "RAG 问答", "Redis 缓存", "限流", "模型切换", "健康检查"]} />
          <Version title="v1.1" items={["Hybrid Search (Dense+BM25+RRF)", "Rerank", "Trace (JSONL)", "Golden Questions 评估", "MCP 工具扩展", "Collections"]} />
          <Version title="v2.0" items={["PDF 内图片提取 + Vision Caption", "图片上传", "文档重新索引", "图片资产管理", "文档详情页", "Docker 健康检查"]} />
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
const chatIcon = <><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></>;
const settingsIcon = <><circle cx="12" cy="12" r="3" /><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" /></>;
const healthIcon = <><path d="M22 12h-4l-3 9L9 3l-3 9H2" /></>;
const evalIcon = <><path d="M9 11l3 3L22 4" /><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" /></>;
