"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";

export default function HealthPage() {
  const [health, setHealth] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    api.getHealth().then(setHealth).catch(console.error).finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const cls = (s: string) => s === "ok" ? "#4caf50" : s === "degraded" ? "#ff9800" : "#f44336";

  return (
    <div>
      <h1>健康检查</h1>
      <button onClick={load} style={{ marginBottom: 16, padding: "8px 20px", cursor: "pointer", borderRadius: 4, border: "1px solid #ccc" }}>
        {loading ? "检查中..." : "刷新"}
      </button>

      {health && (
        <div style={{ display: "grid", gap: 12 }}>
          <StatusCard label="整体状态" value={health.status} color={cls(health.status)} />
          <StatusCard label="SQLite" value={health.sqlite} color={cls(health.sqlite)} />
          <StatusCard label="Redis" value={health.redis} color={cls(health.redis)} />
          <StatusCard label="Chroma" value={health.chroma} color={cls(health.chroma)} />
          <StatusCard label="Provider 汇总" value={health.provider} color={cls(health.provider)} />
          <StatusCard label="Chat Provider" value={health.chat_provider || "unknown"} color={cls(health.chat_provider || "down")} />
          <StatusCard label="Embedding Provider" value={health.embedding_provider || "unknown"} color={cls(health.embedding_provider || "down")} />
          <StatusCard label="Redis 队列长度" value={String(health.redis_queue_length)} color="#555" />
        </div>
      )}
    </div>
  );
}

const StatusCard = ({ label, value, color }: { label: string; value: string; color: string }) => (
  <div style={{ background: "#fff", borderRadius: 8, padding: "14px 18px", display: "flex", justifyContent: "space-between", alignItems: "center", boxShadow: "0 1px 3px rgba(0,0,0,0.1)" }}>
    <span style={{ fontWeight: 600, fontSize: 14 }}>{label}</span>
    <span style={{ color, fontWeight: 700, fontSize: 14, textTransform: "uppercase" }}>{value}</span>
  </div>
);
