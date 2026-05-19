"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function HomePage() {
  const router = useRouter();
  const [health, setHealth] = useState<any>(null);

  useEffect(() => {
    api.getHealth().then(setHealth).catch(() => {});
  }, []);

  return (
    <div>
      <h1 style={{ fontSize: 28, marginBottom: 8 }}>文档 RAG 平台 v2.0</h1>
      <p style={{ color: "#666", fontSize: 14, marginBottom: 24 }}>
        Document RAG Platform — 上传文档，多模态解析，智能问答，可追溯评估
      </p>

      {health && (
        <div style={{ marginBottom: 24, padding: "12px 16px", background: health.status === "ok" ? "#e8f5e9" : "#fff3e0", borderRadius: 6, fontSize: 13, display: "inline-block" }}>
          系统状态: <strong>{health.status}</strong> | SQLite: {health.sqlite} | Redis: {health.redis} | Chroma: {health.chroma}
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 16 }}>
        {[
          { title: "文档管理", desc: "上传、查看、管理文档", href: "/documents" },
          { title: "问答", desc: "RAG 智能问答 + 缓存", href: "/chat" },
          { title: "设置", desc: "模型与 Provider 配置", href: "/settings" },
          { title: "健康检查", desc: "系统组件状态监控", href: "/health" },
          { title: "评估 (v1.1)", desc: "Golden Questions 评估", href: "/evaluations" },
        ].map((card) => (
          <div
            key={card.href}
            onClick={() => router.push(card.href)}
            style={{ background: "#fff", borderRadius: 8, padding: 20, cursor: "pointer", boxShadow: "0 1px 3px rgba(0,0,0,0.1)", transition: "box-shadow 0.2s", border: "1px solid #eee" }}
            onMouseEnter={(e) => (e.currentTarget.style.boxShadow = "0 4px 12px rgba(0,0,0,0.15)")}
            onMouseLeave={(e) => (e.currentTarget.style.boxShadow = "0 1px 3px rgba(0,0,0,0.1)")}
          >
            <h3 style={{ margin: "0 0 8px", fontSize: 16 }}>{card.title}</h3>
            <p style={{ margin: 0, fontSize: 13, color: "#888" }}>{card.desc}</p>
          </div>
        ))}
      </div>

      <div style={{ marginTop: 32, padding: 16, background: "#fff", borderRadius: 8, fontSize: 13, color: "#999" }}>
        <strong>v1 功能:</strong> 文档上传/管理 | 任务状态追踪 | RAG 问答 | Redis 缓存 | 限流 | 模型切换 | 健康检查<br />
        <strong>v1.1 增强:</strong> Hybrid Search (Dense + BM25 + RRF) | Rerank | Trace (JSONL) | Golden Questions 评估 | MCP 工具扩展 | Collections<br />
        <strong>v2.0 新增:</strong> 多模态 (PDF 内图片提取 + Vision Caption) | 图片上传 | 文档重新索引 | 图片资产管理 | 文档详情页 | Docker 健康检查
      </div>
    </div>
  );
}
