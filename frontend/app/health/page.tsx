"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { colors, radius, shadow, font, card } from "@/lib/styles";

export default function HealthPage() {
  const [health, setHealth] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    api.getHealth().then(setHealth).catch(console.error).finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const statusColor = (s: string) => {
    switch (s) {
      case "ok": return colors.success;
      case "degraded": return colors.warn;
      default: return colors.danger;
    }
  };

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: font.xxl, fontWeight: 700, margin: 0 }}>健康检查</h1>
          <p style={{ fontSize: font.sm, color: colors.textSecondary, margin: "4px 0 0" }}>
            系统组件状态监控
          </p>
        </div>
        <button onClick={load} disabled={loading} style={{
          background: colors.surface, color: colors.text, border: `1px solid ${colors.border}`,
          padding: "8px 20px", borderRadius: radius.sm, cursor: "pointer", fontSize: font.sm,
          fontWeight: 500, opacity: loading ? 0.5 : 1,
        }}>
          {loading ? "检查中..." : "刷新"}
        </button>
      </div>

      {health && (
        <div style={{ display: "grid", gap: 10 }}>
          <StatusCard label="整体状态" value={health.status} color={statusColor(health.status)} />
          <StatusCard label="SQLite" value={health.sqlite} color={statusColor(health.sqlite)} />
          <StatusCard label="Redis" value={health.redis} color={statusColor(health.redis)} />
          <StatusCard label="Chroma" value={health.chroma} color={statusColor(health.chroma)} />
          <StatusCard label="Provider 汇总" value={health.provider} color={statusColor(health.provider)} />
          <StatusCard label="Chat Provider" value={health.chat_provider || "unknown"} color={statusColor(health.chat_provider || "down")} />
          <StatusCard label="Embedding Provider" value={health.embedding_provider || "unknown"} color={statusColor(health.embedding_provider || "down")} />
          <StatusCard label="Redis 队列长度" value={String(health.redis_queue_length)} color={colors.text} />
        </div>
      )}
    </div>
  );
}

const StatusCard = ({ label, value, color: clr }: { label: string; value: string; color: string }) => (
  <div style={{
    ...card, display: "flex", justifyContent: "space-between", alignItems: "center",
    padding: "14px 20px", marginBottom: 0,
  }}>
    <span style={{ fontWeight: 600, fontSize: font.sm }}>{label}</span>
    <span style={{
      color: clr, fontWeight: 700, fontSize: font.xs, textTransform: "uppercase",
      display: "inline-flex", alignItems: "center", gap: 6,
    }}>
      <span style={{
        width: 8, height: 8, borderRadius: "50%", background: clr, display: "inline-block",
      }} />
      {value}
    </span>
  </div>
);
