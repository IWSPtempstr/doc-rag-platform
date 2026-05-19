"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { Document } from "@/lib/types";

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
      setMessage(`上传成功! document_id=${result.document_id}`);
      load();
    } catch (err: any) {
      setMessage(`上传失败: ${err.message}`);
    }
    setUploading(false);
  };

  const handleDelete = async (id: number) => {
    if (!confirm("确认删除？")) return;
    await api.deleteDocument(id);
    load();
  };

  const handleReindex = async (id: number) => {
    if (!confirm("确认重新索引？")) return;
    try {
      const result: any = await api.reindexDocument(id);
      setMessage(`重新索引已提交: job_id=${result.job_id}`);
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

  const statusColor = (s: string) => {
    switch (s) {
      case "completed": return "#4caf50";
      case "processing": return "#ff9800";
      case "failed": return "#f44336";
      default: return "#999";
    }
  };

  return (
    <div>
      <h1>文档管理</h1>

      {/* Search and filters */}
      <div style={{ marginBottom: 16, display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <label style={{ cursor: "pointer", background: "#1a1a2e", color: "#fff", padding: "8px 16px", borderRadius: 4, fontSize: 14 }}>
          {uploading ? "上传中..." : "上传文档"}
          <input type="file" accept=".pdf,.docx,.md,.txt,.png,.jpg,.jpeg,.gif,.webp,.bmp" onChange={handleUpload} style={{ display: "none" }} />
        </label>
        <input
          placeholder="搜索文件名..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ padding: "6px 12px", borderRadius: 4, border: "1px solid #ccc", fontSize: 14 }}
        />
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
          style={{ padding: "6px 12px", borderRadius: 4, border: "1px solid #ccc", fontSize: 14 }}>
          <option value="">全部状态</option>
          <option value="pending">pending</option>
          <option value="processing">processing</option>
          <option value="completed">completed</option>
          <option value="failed">failed</option>
        </select>
        <select value={hasImagesFilter} onChange={(e) => setHasImagesFilter(e.target.value)}
          style={{ padding: "6px 12px", borderRadius: 4, border: "1px solid #ccc", fontSize: 14 }}>
          <option value="">全部类型</option>
          <option value="true">含图片</option>
          <option value="false">纯文本</option>
        </select>
        {message && <span style={{ color: message.includes("失败") ? "#f44336" : "#4caf50", fontSize: 14 }}>{message}</span>}
      </div>

      {/* Batch action bar */}
      {selected.size > 0 && (
        <div style={{ marginBottom: 8, padding: "8px 12px", background: "#fff3e0", borderRadius: 4, display: "flex", gap: 8, alignItems: "center" }}>
          <span style={{ fontSize: 13 }}>已选 {selected.size} 项</span>
          <button onClick={batchDelete} style={{ background: "#f44336", color: "#fff", border: "none", padding: "4px 12px", borderRadius: 4, cursor: "pointer", fontSize: 13 }}>批量删除</button>
        </div>
      )}

      <table style={{ width: "100%", borderCollapse: "collapse", background: "#fff", borderRadius: 8, overflow: "hidden" }}>
        <thead>
          <tr style={{ background: "#1a1a2e", color: "#fff" }}>
            <th style={thStyle}><input type="checkbox" checked={selected.size === docs.length && docs.length > 0} onChange={toggleAll} /></th>
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
            <tr key={d.id} style={{ borderBottom: "1px solid #eee", background: selected.has(d.id) ? "#e3f2fd" : undefined }}>
              <td style={tdStyle}><input type="checkbox" checked={selected.has(d.id)} onChange={() => toggleSelect(d.id)} /></td>
              <td style={tdStyle}>{d.id}</td>
              <td style={{ ...tdStyle, cursor: "pointer", color: "#1976d2" }}
                onClick={() => router.push(`/documents/${d.id}`)}>
                {d.filename}
              </td>
              <td style={tdStyle}>{d.content_type}</td>
              <td style={tdStyle}>{formatSize(d.size_bytes)}</td>
              <td style={tdStyle}><span style={{ color: statusColor(d.status), fontWeight: 600 }}>{d.status}</span></td>
              <td style={tdStyle}>{d.chunk_count}</td>
              <td style={tdStyle}>{d.image_count > 0 ? d.image_count : "-"}</td>
              <td style={tdStyle}>{d.tags || "-"}</td>
              <td style={tdStyle}>
                <button onClick={() => handleReindex(d.id)} style={reindexBtnStyle}>重索引</button>
                <button onClick={() => handleDelete(d.id)} style={deleteBtnStyle}>删除</button>
              </td>
            </tr>
          ))}
          {docs.length === 0 && (
            <tr><td colSpan={10} style={{ padding: 24, textAlign: "center", color: "#999" }}>暂无文档，请上传</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

const thStyle: React.CSSProperties = { padding: "10px 8px", textAlign: "left", fontSize: 12 };
const tdStyle: React.CSSProperties = { padding: "8px", fontSize: 13 };
const reindexBtnStyle: React.CSSProperties = { background: "#ff9800", color: "#fff", border: "none", padding: "4px 8px", borderRadius: 4, cursor: "pointer", marginRight: 6, fontSize: 12 };
const deleteBtnStyle: React.CSSProperties = { background: "#f44336", color: "#fff", border: "none", padding: "4px 8px", borderRadius: 4, cursor: "pointer", fontSize: 12 };

function formatSize(bytes: number) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}
