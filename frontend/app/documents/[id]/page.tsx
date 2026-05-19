"use client";

import { useState, useEffect, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { Document, DocumentChunk, ImageAsset, Job } from "@/lib/types";

export default function DocumentDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = Number(params.id);

  const [doc, setDoc] = useState<Document | null>(null);
  const [chunks, setChunks] = useState<DocumentChunk[]>([]);
  const [assets, setAssets] = useState<ImageAsset[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [editFilename, setEditFilename] = useState("");
  const [editTags, setEditTags] = useState("");
  const [message, setMessage] = useState("");

  const loadDoc = useCallback(() => {
    api.getDocument(id).then((d) => {
      const docData = d as Document;
      setDoc(docData);
      setEditFilename(docData.filename);
      setEditTags(docData.tags);
    }).catch(console.error);
  }, [id]);

  const loadAll = useCallback(() => {
    loadDoc();
    api.getDocumentChunks(id).then(setChunks).catch(() => setChunks([]));
    api.getDocumentAssets(id).then(setAssets).catch(() => setAssets([]));
    api.getDocumentJobs(id).then(setJobs).catch(() => setJobs([]));
  }, [id, loadDoc]);

  useEffect(() => { loadAll(); }, [loadAll]);

  // Poll while processing
  useEffect(() => {
    if (!doc || doc.status !== "processing") return;
    const t = setInterval(loadAll, 3000);
    return () => clearInterval(t);
  }, [doc?.status, loadAll]);

  const handleSaveMeta = async () => {
    try {
      const result = await api.updateDocument(id, { filename: editFilename, tags: editTags }) as Document;
      setDoc(result);
      setMessage("保存成功");
    } catch (err: any) {
      setMessage(`保存失败: ${err.message}`);
    }
  };

  const handleReindex = async () => {
    if (!confirm("确认重新索引？将重新提取文本、图片和生成描述。")) return;
    try {
      const result = await api.reindexDocument(id) as any;
      setMessage(`重新索引已提交: job_id=${result.job_id}`);
      loadAll();
    } catch (err: any) {
      setMessage(`失败: ${err.message}`);
    }
  };

  const handleDelete = async () => {
    if (!confirm("确认删除此文档？此操作不可撤销。")) return;
    await api.deleteDocument(id);
    router.push("/documents");
  };

  const statusColor = (s: string) => {
    switch (s) {
      case "completed": return "#4caf50";
      case "processing": return "#ff9800";
      case "failed": return "#f44336";
      default: return "#999";
    }
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  };

  if (!doc) return <div style={{ padding: 24, color: "#999" }}>加载中...</div>;

  const latestJob = jobs.length > 0 ? jobs[0] : null;
  const latestJobProgress = latestJob?.progress;

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <a onClick={() => router.push("/documents")} style={{ color: "#1976d2", cursor: "pointer", fontSize: 14 }}>
          &larr; 返回文档列表
        </a>
      </div>

      {message && (
        <div style={{ marginBottom: 12, padding: "8px 12px", borderRadius: 4,
          background: message.includes("失败") ? "#ffebee" : "#e8f5e9",
          color: message.includes("失败") ? "#c62828" : "#2e7d32", fontSize: 14 }}>
          {message}
        </div>
      )}

      {/* Metadata Card */}
      <div style={cardStyle}>
        <h2 style={{ margin: "0 0 16px 0" }}>文档信息</h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 12 }}>
          <Field label="文件名" value={editFilename} onChange={setEditFilename} />
          <Field label="标签" value={editTags} onChange={setEditTags} />
          <ReadOnly label="类型" value={doc.content_type} />
          <ReadOnly label="大小" value={formatSize(doc.size_bytes)} />
          <ReadOnly label="状态" value={<span style={{ color: statusColor(doc.status), fontWeight: 600 }}>{doc.status}</span>} />
          <ReadOnly label="Chunks" value={String(doc.chunk_count)} />
          <ReadOnly label="图片数" value={String(doc.image_count)} />
          <ReadOnly label="版本" value={`v${doc.kb_version}`} />
          <ReadOnly label="创建时间" value={new Date(doc.created_at).toLocaleString()} />
        </div>
        <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
          <button onClick={handleSaveMeta} style={btnPrimary}>保存修改</button>
          <button onClick={handleReindex} style={btnWarn}>重新索引</button>
          <button onClick={handleDelete} style={btnDanger}>删除文档</button>
        </div>
      </div>

      {/* Latest Job Card */}
      {latestJob && (
        <div style={cardStyle}>
          <h3 style={{ margin: "0 0 8px 0" }}>
            最近任务: {latestJob.type}
            <span style={{ color: statusColor(latestJob.status), marginLeft: 8 }}>
              {latestJob.status}
            </span>
          </h3>
          {latestJobProgress && (
            <div>
              <div style={{ fontSize: 13, color: "#666" }}>
                阶段: {latestJobProgress.stage} — {latestJobProgress.message}
              </div>
              {latestJob.status === "processing" && (
                <div style={{ marginTop: 4, height: 4, background: "#e0e0e0", borderRadius: 2 }}>
                  <div style={{ height: 4, background: "#ff9800", borderRadius: 2, width: "60%" }} />
                </div>
              )}
            </div>
          )}
          {latestJob.error && <div style={{ color: "#f44336", fontSize: 13, marginTop: 4 }}>错误: {latestJob.error}</div>}
        </div>
      )}

      {/* Chunks Section */}
      <div style={cardStyle}>
        <h3 style={{ margin: "0 0 12px 0" }}>Chunks ({chunks.length})</h3>
        {chunks.length === 0 && <div style={{ color: "#999", fontSize: 14 }}>暂无 chunks</div>}
        {chunks.map((c) => (
          <details key={c.chunk_id} style={{ marginBottom: 8, border: "1px solid #eee", borderRadius: 6, padding: 10 }}>
            <summary style={{ cursor: "pointer", fontSize: 13, fontWeight: 600 }}>
              {c.chunk_id} — {c.metadata.char_count} 字符
              {c.metadata.page_range && ` — 第 ${c.metadata.page_range.join(",")} 页`}
              {c.image_refs.length > 0 && ` — ${c.image_refs.length} 张图片`}
            </summary>
            <pre style={{ whiteSpace: "pre-wrap", fontSize: 12, color: "#333", marginTop: 8, background: "#fafafa", padding: 8, borderRadius: 4 }}>
              {c.content.length > 500 ? c.content.slice(0, 500) + "..." : c.content}
            </pre>
            {c.image_refs.length > 0 && (
              <div style={{ marginTop: 8 }}>
                <div style={{ fontSize: 12, color: "#666", marginBottom: 4 }}>关联图片:</div>
                {c.image_refs.map((ref) => (
                  <span key={ref.asset_id} style={{ display: "inline-block", marginRight: 8, fontSize: 12,
                    background: "#e3f2fd", padding: "2px 8px", borderRadius: 4 }}>
                    {ref.filename} {ref.caption && `— ${ref.caption.slice(0, 40)}...`}
                  </span>
                ))}
              </div>
            )}
          </details>
        ))}
      </div>

      {/* Assets Section */}
      <div style={cardStyle}>
        <h3 style={{ margin: "0 0 12px 0" }}>图片资产 ({assets.length})</h3>
        {assets.length === 0 && <div style={{ color: "#999", fontSize: 14 }}>暂无图片资产</div>}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(250px, 1fr))", gap: 12 }}>
          {assets.map((a) => (
            <div key={a.id} style={{ border: "1px solid #eee", borderRadius: 8, padding: 12, background: "#fafafa" }}>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>{a.filename}</div>
              <div style={{ fontSize: 12, color: "#666" }}>类型: {a.content_type}</div>
              <div style={{ fontSize: 12, color: "#666" }}>大小: {formatSize(a.size_bytes)}</div>
              {a.source_page && <div style={{ fontSize: 12, color: "#666" }}>页码: 第 {a.source_page} 页</div>}
              {a.caption ? (
                <div style={{ fontSize: 12, color: "#333", marginTop: 6, fontStyle: "italic", background: "#fff", padding: 6, borderRadius: 4 }}>
                  {a.caption}
                </div>
              ) : (
                <div style={{ fontSize: 12, color: "#999", marginTop: 6 }}>无描述</div>
              )}
              {a.associated_chunks && a.associated_chunks.length > 0 && (
                <div style={{ marginTop: 6, fontSize: 11, color: "#888" }}>
                  关联: {a.associated_chunks.join(", ")}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Job History */}
      <div style={cardStyle}>
        <h3 style={{ margin: "0 0 12px 0" }}>任务历史 ({jobs.length})</h3>
        {jobs.length === 0 && <div style={{ color: "#999", fontSize: 14 }}>暂无任务记录</div>}
        {jobs.map((j) => (
          <div key={j.id} style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 0", borderBottom: "1px solid #f0f0f0", fontSize: 13 }}>
            <span style={{ minWidth: 40 }}>#{j.id}</span>
            <span style={{ minWidth: 80, fontWeight: 600 }}>{j.type}</span>
            <span style={{ color: statusColor(j.status), minWidth: 80 }}>{j.status}</span>
            <span style={{ color: "#999" }}>{new Date(j.created_at).toLocaleString()}</span>
            {j.error && <span style={{ color: "#f44336", flex: 1 }}>{j.error.slice(0, 80)}</span>}
          </div>
        ))}
      </div>
    </div>
  );
}

/* ---- Helper Components ---- */

function Field({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div>
      <div style={{ fontSize: 11, color: "#999", marginBottom: 2 }}>{label}</div>
      <input value={value} onChange={(e) => onChange(e.target.value)}
        style={{ width: "100%", padding: "6px 10px", border: "1px solid #ddd", borderRadius: 4, fontSize: 13, boxSizing: "border-box" }} />
    </div>
  );
}

function ReadOnly({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <div style={{ fontSize: 11, color: "#999", marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: 13, padding: "6px 0" }}>{value}</div>
    </div>
  );
}

/* ---- Styles ---- */

const cardStyle: React.CSSProperties = {
  background: "#fff",
  borderRadius: 8,
  padding: 20,
  marginBottom: 16,
  border: "1px solid #eee",
  boxShadow: "0 1px 3px rgba(0,0,0,0.06)",
};

const btnPrimary: React.CSSProperties = {
  background: "#1a1a2e", color: "#fff", border: "none",
  padding: "8px 18px", borderRadius: 4, cursor: "pointer", fontSize: 13,
};

const btnWarn: React.CSSProperties = {
  background: "#ff9800", color: "#fff", border: "none",
  padding: "8px 18px", borderRadius: 4, cursor: "pointer", fontSize: 13,
};

const btnDanger: React.CSSProperties = {
  background: "#f44336", color: "#fff", border: "none",
  padding: "8px 18px", borderRadius: 4, cursor: "pointer", fontSize: 13,
};
