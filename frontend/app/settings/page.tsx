"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { colors, radius, shadow, font, btnPrimary, inputBase, card } from "@/lib/styles";

export default function SettingsPage() {
  const [settings, setSettings] = useState<any>({
    provider: "openai",
    chat_provider: "openai",
    embedding_provider: "openai",
    chat_model: "Pro/zai-org/GLM-5.1",
    embed_model: "Qwen/Qwen3-VL-Embedding-8B",
    top_k: 5,
    stream: true,
    vision_provider: "openai",
    vision_model: "Qwen/Qwen3.6-35B-A3B",
  });
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api.getSettings().then(setSettings).catch(console.error);
  }, []);

  const handleSave = async () => {
    await api.updateSettings(settings);
    setSaved(true);
    setTimeout(() => setSaved(false), 2500);
  };

  const update = (key: string, value: any) => setSettings((s: any) => ({ ...s, [key]: value }));

  const selectStyle: React.CSSProperties = { ...inputBase, width: "100%", cursor: "pointer", color: colors.text };

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: font.xxl, fontWeight: 700, margin: 0 }}>模型设置</h1>
        <p style={{ fontSize: font.sm, color: colors.textSecondary, margin: "4px 0 0" }}>
          配置 Chat 和 Embedding Provider
        </p>
      </div>

      <div style={{ ...card, maxWidth: 520, padding: 24 }}>
        <Field label="Chat Provider">
          <select value={settings.chat_provider || settings.provider} onChange={(e) => {
            update("chat_provider", e.target.value);
            update("provider", e.target.value);
          }} style={selectStyle}>
            <option value="openai">OpenAI / Compatible</option>
            <option value="ollama">Ollama</option>
          </select>
        </Field>

        <Field label="Embedding Provider">
          <select value={settings.embedding_provider} onChange={(e) => update("embedding_provider", e.target.value)} style={selectStyle}>
            <option value="openai">OpenAI / Compatible</option>
            <option value="ollama">Ollama</option>
          </select>
        </Field>

        <Field label="Chat Model">
          <input value={settings.chat_model} onChange={(e) => update("chat_model", e.target.value)}
            style={{ ...inputBase, width: "100%" }} placeholder="deepseek-v4-flash" />
        </Field>

        <Field label="Embed Model">
          <input value={settings.embed_model} onChange={(e) => update("embed_model", e.target.value)}
            style={{ ...inputBase, width: "100%" }} placeholder="Qwen/Qwen3-VL-Embedding-8B" />
        </Field>

        <Field label="Vision Model">
          <input value={settings.vision_model || ""} onChange={(e) => update("vision_model", e.target.value)}
            style={{ ...inputBase, width: "100%" }} placeholder="Qwen/Qwen3.6-35B-A3B" />
        </Field>

        <Field label="Top K">
          <input type="number" value={settings.top_k} onChange={(e) => update("top_k", parseInt(e.target.value) || 5)}
            style={{ ...inputBase, width: 100 }} min={1} max={50} />
        </Field>

        <Field label="Stream">
          <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", fontSize: font.sm }}>
            <input type="checkbox" checked={settings.stream} onChange={(e) => update("stream", e.target.checked)}
              style={{ width: 16, height: 16, accentColor: colors.primary }} />
            启用流式输出
          </label>
        </Field>

        <button onClick={handleSave} style={{
          ...btnPrimary, padding: "10px 32px", marginTop: 8,
          background: saved ? colors.success : colors.primary,
          transition: "background 0.2s",
        }}>
          {saved ? "✓ 已保存" : "保存设置"}
        </button>
      </div>
    </div>
  );
}

const Field = ({ label, children }: { label: string; children: React.ReactNode }) => (
  <div style={{ marginBottom: 18 }}>
    <label style={{ display: "block", fontSize: font.xs, fontWeight: 600, marginBottom: 6, color: colors.textSecondary, textTransform: "uppercase", letterSpacing: "0.3px" }}>{label}</label>
    {children}
  </div>
);
