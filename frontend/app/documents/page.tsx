"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { Document } from "@/lib/types";
import { colors, radius, shadow, font, badge, btnPrimary, btnDanger, inputBase } from "@/lib/styles";

export default function DocumentsPage() {
  const router = useRouter();
  const [docs, setDocs] = useState<Document[]>([]);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [hasImagesFilter, setHasImagesFilter] = useState<string>("");
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState("");
  const [selected, setSelected] = useState<Set<number>>(new Set());

  const load = useCallback(() => {
    const params: any = {};
    if (search) params.search = search;
    if (statusFilter) params.status = statusFilter;
    if (hasImagesFilter === "true") params.has_images = true;
    else if (hasImagesFilter === "false") params.has_images = false;
    api.listDocuments(params).then(setDocs).catch(console.error);
  }, [search, statusFilter, hasImagesFilter]);

  useEffect(() => { load(); }, [load]);

  // Auto-refresh when any doc is processing
  useEffect(() => {
    const hasProcessing = docs.some((d) => d.status === "processing");
    if (!hasProcessing) return;
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [docs, load]);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setMessage("");
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("tags", "");
      const result: any = await api.uploadDocument(fd);
      setMessage(`上传成功 — ID: ${result.document_id}`);
      load();
    } catch (err: any) {
      setMessage(`上传失败: ${err.message}`);
    }
    setUploading(false);
  };

  const handleDelete = async (id: number) => {
    if (!confirm("确认删除此文档？")) return;
    await api.deleteDocument(id);
    load();
  };

  const handleReindex = async (id: number) => {
    if (!confirm("确认重新索引？")) return;
    try {
      const result: any = await api.reindexDocument(id);
      setMessage(`重新索引已提交 — Job #${result.job_id}`);
      load();
    } catch (err: any) {
      setMessage(`重新索引失败: ${err.message}`);
    }
  };

  const toggleSelect = (id: number) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id); else next.add(id);
    setSelected(next);
  };

  const toggleAll = () => {
    if (selected.size === docs.length) setSelected(new Set());
    else setSelected(new Set(docs.map((d) => d.id)));
  };

  const batchDelete = async () => {
    if (!confirm(`确认删除 ${selected.size} 个文档？`)) return;
    for (const id of selected) {
      try { await api.deleteDocument(id); } catch (e) {}
    }
    setSelected(new Set());
    load();
  };

  const selectStyle = {
    ...inputBase,
    width: 110,
    cursor: "pointer",
    color: colors.text,
  };

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
        <h1 style={{ fontSize: font.xxl, fontWeight: 700, margin: 0 }}>文档管理</h1>
        <span style={{ fontSize: font.xs, color: colors.textMuted }}>{docs.length} 个文档</span>
      </div>

      {/* Toolbar */}
      <div style={{
        background: colors.surface, borderRadius: radius.lg, padding: "14px 18px",
        marginBottom: 16, border: `1px solid ${colors.border}`, boxShadow: shadow.sm,
        display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap",
      }}>
        <label style={{
          ...btnPrimary, display: "inline-flex", alignItems: "center", gap: 6,
          padding: "9px 20px", borderRadius: radius.sm, opacity: uploading ? 0.6 : 1,
        }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 5v14M5 12h14"/>
          </svg>
          {uploading ? "上传中..." : "上传文档"}
          <input type="file" accept=".pdf,.docx,.md,.txt,.png,.jpg,.jpeg,.gif,.webp,.bmp"
            onChange={handleUpload} style={{ display: "none" }} />
        </label>

        <input
          placeholder="搜索文件名..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ ...inputBase, flex: 1, minWidth: 180 }}
        />

        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} style={selectStyle}>
          <option value="">全部状态</option>
          <option value="pending">待处理</option>
          <option value="processing">处理中</option>
          <option value="completed">已完成</option>
          <option value="failed">失败</option>
        </select>

        <select value={hasImagesFilter} onChange={(e) => setHasImagesFilter(e.target.value)} style={selectStyle}>
          <option value="">全部类型</option>
          <option value="true">含图片</option>
          <option value="false">纯文本</option>
        </select>

        {message && (
          <span style={{
            fontSize: font.sm, padding: "4px 12px", borderRadius: radius.sm,
            background: message.includes("失败") ? "#fef2f2" : "#ecfdf5",
            color: message.includes("失败") ? colors.danger : colors.success,
          }}>{message}</span>
        )}
      </div>

      {/* Batch action bar */}
      {selected.size > 0 && (
        <div style={{
          marginBottom: 12, padding: "10px 16px", background: "#eff6ff", borderRadius: radius.md,
          display: "flex", gap: 10, alignItems: "center", border: `1px solid #bfdbfe`,
        }}>
          <span style={{ fontSize: font.sm, fontWeight: 600, color: colors.primary }}>已选 {selected.size} 项</span>
          <button onClick={batchDelete} style={btnDanger}>批量删除</button>
          <button onClick={() => setSelected(new Set())} style={{
            background: "transparent", color: colors.textSecondary, border: "none", cursor: "pointer", fontSize: font.xs,
          }}>取消选择</button>
        </div>
      )}

      {/* Table */}
      <div style={{
        background: colors.surface, borderRadius: radius.lg, overflow: "hidden",
        border: `1px solid ${colors.border}`, boxShadow: shadow.sm,
      }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ background: "#f8fafc", borderBottom: `2px solid ${colors.border}` }}>
              <th style={thStyle}><input type="checkbox" checked={selected.size === docs.length && docs.length > 0} onChange={toggleAll}
                style={{ width: 14, height: 14, cursor: "pointer", accentColor: colors.primary }} /></th>
              <th style={thStyle}>ID</th>
              <th style={thStyle}>文件名</th>
              <th style={thStyle}>类型</th>
              <th style={thStyle}>大小</th>
              <th style={thStyle}>状态</th>
              <th style={thStyle}>Chunks</th>
              <th style={thStyle}>图片</th>
              <th style={thStyle}>标签</th>
              <th style={thStyle}>操作</th>
            </tr>
          </thead>
          <tbody>
            {docs.map((d) => (
              <tr key={d.id} style={{
                borderBottom: `1px solid ${colors.borderLight}`,
                background: selected.has(d.id) ? colors.selected : undefined,
                transition: "background 0.1s",
              }}
                onMouseEnter={(e) => { if (!selected.has(d.id)) e.currentTarget.style.background = colors.hover; }}
                onMouseLeave={(e) => { if (!selected.has(d.id)) e.currentTarget.style.background = ""; }}
              >
                <td style={tdStyle}>
                  <input type="checkbox" checked={selected.has(d.id)} onChange={() => toggleSelect(d.id)}
                    style={{ width: 14, height: 14, cursor: "pointer", accentColor: colors.primary }} />
                </td>
                <td style={{ ...tdStyle, color: colors.textMuted, fontSize: font.xs }}>{d.id}</td>
                <td style={{ ...tdStyle, cursor: "pointer", color: colors.accent, fontWeight: 500 }}
                  onClick={() => router.push(`/documents/${d.id}`)}>
                  {d.filename}
                </td>
                <td style={tdStyle}>
                  <span style={{
                    display: "inline-block", padding: "1px 8px", borderRadius: 4,
                    background: colors.borderLight, fontSize: font.xs, color: colors.textSecondary,
                    textTransform: "uppercase", fontWeight: 600,
                  }}>{d.content_type}</span>
                </td>
                <td style={{ ...tdStyle, color: colors.textSecondary }}>{formatSize(d.size_bytes)}</td>
                <td style={tdStyle}><span style={badge(d.status)}>{d.status}</span></td>
                <td style={{ ...tdStyle, textAlign: "center" }}>{d.chunk_count || "-"}</td>
                <td style={{ ...tdStyle, textAlign: "center" }}>
                  {d.image_count > 0 ? (
                    <span style={{ fontSize: font.xs, fontWeight: 600, color: colors.accent }}>
                      {d.image_count}
                    </span>
                  ) : "-"}
                </td>
                <td style={tdStyle}>
                  {d.tags ? (
                    <span style={{ fontSize: font.xs, color: colors.textSecondary, background: colors.borderLight, padding: "1px 6px", borderRadius: 4 }}>
                      {d.tags}
                    </span>
                  ) : "-"}
                </td>
                <td style={tdStyle}>
                  <button onClick={() => handleReindex(d.id)}
                    style={{
                      background: "transparent", color: colors.warn, border: `1px solid #fcd34d`,
                      padding: "4px 10px", borderRadius: radius.sm, cursor: "pointer", fontSize: font.xs,
                      fontWeight: 500, marginRight: 6,
                    }}>重索引</button>
                  <button onClick={() => handleDelete(d.id)}
                    style={{
                      background: "transparent", color: colors.danger, border: `1px solid #fecaca`,
                      padding: "4px 10px", borderRadius: radius.sm, cursor: "pointer", fontSize: font.xs,
                      fontWeight: 500,
                    }}>删除</button>
                </td>
              </tr>
            ))}
            {docs.length === 0 && (
              <tr>
                <td colSpan={10} style={{ padding: 48, textAlign: "center" }}>
                  <div style={{ fontSize: 36, marginBottom: 8, opacity: 0.3 }}>&#128196;</div>
                  <div style={{ color: colors.textMuted, fontSize: font.base }}>暂无文档</div>
                  <div style={{ color: colors.textMuted, fontSize: font.xs, marginTop: 4 }}>上传 PDF、DOCX、MD、TXT 或图片文件</div>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const thStyle: React.CSSProperties = {
  padding: "10px 10px", textAlign: "left", fontSize: 11, fontWeight: 600,
  color: "#6b7280", textTransform: "uppercase", letterSpacing: "0.5px",
};

const tdStyle: React.CSSProperties = { padding: "10px 10px", fontSize: 13 };

function formatSize(bytes: number) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}
