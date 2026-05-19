"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";

export default function SettingsPage() {
  const [settings, setSettings] = useState<any>({
    provider: "openai",
    chat_provider: "openai",
    embedding_provider: "ollama",
    chat_model: "deepseek-v4-flash",
    embed_model: "nomic-embed-text",
    top_k: 5,
    stream: true,
  });
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api.getSettings().then(setSettings).catch(console.error);
  }, []);

  const handleSave = async () => {
    await api.updateSettings(settings);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const update = (key: string, value: any) => setSettings((s: any) => ({ ...s, [key]: value }));

  return (
    <div>
      <h1>模型设置</h1>
      <div style={{ background: "#fff", borderRadius: 8, padding: 24, boxShadow: "0 1px 3px rgba(0,0,0,0.1)", maxWidth: 480 }}>
        <Field label="Chat Provider">
          <select value={settings.chat_provider || settings.provider} onChange={(e) => {
            update("chat_provider", e.target.value);
            update("provider", e.target.value);
          }} style={inputStyle}>
            <option value="openai">OpenAI / Compatible</option>
            <option value="ollama">Ollama</option>
          </select>
        </Field>
        <Field label="Embedding Provider">
          <select value={settings.embedding_provider} onChange={(e) => update("embedding_provider", e.target.value)} style={inputStyle}>
            <option value="ollama">Ollama</option>
            <option value="openai">OpenAI / Compatible</option>
          </select>
        </Field>
        <Field label="Chat Model">
          <input value={settings.chat_model} onChange={(e) => update("chat_model", e.target.value)} style={inputStyle} placeholder="deepseek-v4-flash" />
        </Field>
        <Field label="Embed Model">
          <input value={settings.embed_model} onChange={(e) => update("embed_model", e.target.value)} style={inputStyle} placeholder="nomic-embed-text" />
        </Field>
        <Field label="Top K">
          <input type="number" value={settings.top_k} onChange={(e) => update("top_k", parseInt(e.target.value) || 5)} style={inputStyle} min={1} max={50} />
        </Field>
        <Field label="Stream">
          <input type="checkbox" checked={settings.stream} onChange={(e) => update("stream", e.target.checked)} />
        </Field>
        <button onClick={handleSave} style={{ padding: "10px 28px", background: saved ? "#4caf50" : "#1a1a2e", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer", fontWeight: 600 }}>
          {saved ? "已保存" : "保存设置"}
        </button>
      </div>
    </div>
  );
}

const Field = ({ label, children }: { label: string; children: React.ReactNode }) => (
  <div style={{ marginBottom: 16 }}>
    <label style={{ display: "block", fontSize: 13, fontWeight: 600, marginBottom: 6, color: "#555" }}>{label}</label>
    {children}
  </div>
);

const inputStyle: React.CSSProperties = { width: "100%", padding: "8px 12px", borderRadius: 4, border: "1px solid #ccc", fontSize: 14, boxSizing: "border-box" };
