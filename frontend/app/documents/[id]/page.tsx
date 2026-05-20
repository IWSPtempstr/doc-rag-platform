"use client";

import { useState, useEffect, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { Document, DocumentChunk, ImageAsset, Job } from "@/lib/types";
import { colors, radius, shadow, font, badge, btnPrimary, btnDanger, btnGhost, inputBase, card } from "@/lib/styles";

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

  if (!doc) return (
    <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: 200 }}>
      <span style={{ color: colors.textMuted, fontSize: font.md }}>加载中...</span>
    </div>
  );

  const latestJob = jobs.length > 0 ? jobs[0] : null;
  const latestJobProgress = latestJob?.progress;

  return (
    <div>
      {/* Header */}
      <div style={{ marginBottom: 20 }}>
        <a onClick={() => router.push("/documents")}
          style={{ color: colors.accent, cursor: "pointer", fontSize: font.sm, fontWeight: 500, textDecoration: "none" }}>
          &larr; 返回文档列表
        </a>
        <h1 style={{ fontSize: font.xxl, fontWeight: 700, margin: "12px 0 0" }}>{doc.filename}</h1>
      </div>

      {message && (
        <div style={{
          marginBottom: 12, padding: "10px 16px", borderRadius: radius.sm, fontSize: font.sm,
          background: message.includes("失败") ? "#fef2f2" : "#ecfdf5",
          color: message.includes("失败") ? colors.danger : colors.success,
          border: `1px solid ${message.includes("失败") ? "#fecaca" : "#a7f3d0"}`,
        }}>{message}</div>
      )}

      {/* Metadata Card */}
      <div style={card}>
        <h2 style={{ margin: "0 0 16px 0", fontSize: font.lg, fontWeight: 600 }}>文档信息</h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 14 }}>
          <Field label="文件名" value={editFilename} onChange={setEditFilename} />
          <Field label="标签" value={editTags} onChange={setEditTags} />
          <ReadOnly label="类型" value={doc.content_type} />
          <ReadOnly label="大小" value={formatSize(doc.size_bytes)} />
          <ReadOnly label="状态" value={<span style={badge(doc.status)}>{doc.status}</span>} />
          <ReadOnly label="Chunks" value={String(doc.chunk_count)} />
          <ReadOnly label="图片数" value={String(doc.image_count)} />
          <ReadOnly label="版本" value={`v${doc.kb_version}`} />
          <ReadOnly label="创建时间" value={new Date(doc.created_at).toLocaleString()} />
        </div>
        <div style={{ marginTop: 16, display: "flex", gap: 10 }}>
          <button onClick={handleSaveMeta} style={btnPrimary}>保存修改</button>
          <button onClick={handleReindex} style={{ ...btnGhost, color: colors.warn, borderColor: "#fcd34d" }}>重新索引</button>
          <button onClick={handleDelete} style={btnDanger}>删除文档</button>
        </div>
      </div>

      {/* Latest Job Card */}
      {latestJob && (
        <div style={card}>
          <h3 style={{ margin: "0 0 12px 0", fontSize: font.md, fontWeight: 600, display: "flex", alignItems: "center", gap: 10 }}>
            最近任务: {latestJob.type}
            <span style={badge(latestJob.status)}>{latestJob.status}</span>
          </h3>
          {latestJobProgress && (
            <div>
              <div style={{ fontSize: font.sm, color: colors.textSecondary, marginBottom: 8 }}>
                阶段: {latestJobProgress.stage} — {latestJobProgress.message}
              </div>
              {latestJob.status === "processing" && (
                <div style={{ height: 6, background: colors.border, borderRadius: 3, overflow: "hidden" }}>
                  <div style={{
                    height: 6, background: colors.warn, borderRadius: 3,
                    width: "60%", transition: "width 1s ease",
                  }} />
                </div>
              )}
            </div>
          )}
          {latestJob.error && (
            <div style={{ color: colors.danger, fontSize: font.sm, marginTop: 8, padding: "8px 12px", background: "#fef2f2", borderRadius: radius.sm }}>
              错误: {latestJob.error}
            </div>
          )}
        </div>
      )}

      {/* Chunks Section */}
      <div style={card}>
        <h3 style={{ margin: "0 0 14px 0", fontSize: font.md, fontWeight: 600, display: "flex", alignItems: "center", gap: 8 }}>
          Chunks
          <span style={{ fontSize: font.xs, color: colors.textMuted, fontWeight: 400 }}>({chunks.length})</span>
        </h3>
        {chunks.length === 0 && (
          <div style={{ color: colors.textMuted, fontSize: font.sm, textAlign: "center", padding: 32 }}>暂无 chunks</div>
        )}
        {chunks.map((c) => (
          <details key={c.chunk_id} style={{
            marginBottom: 8, border: `1px solid ${colors.border}`, borderRadius: radius.md,
            background: colors.surface, overflow: "hidden",
          }}>
            <summary style={{
              cursor: "pointer", fontSize: font.sm, fontWeight: 600, padding: "10px 14px",
              background: colors.hover, userSelect: "none",
            }}>
              <span style={{ color: colors.textMuted, fontSize: font.xs, marginRight: 8 }}>{c.chunk_id}</span>
              {c.metadata.char_count} 字符
              {c.metadata.page_range && <span style={{ marginLeft: 8, color: colors.textSecondary }}>— 第 {c.metadata.page_range.join(",")} 页</span>}
              {c.image_refs.length > 0 && (
                <span style={{ marginLeft: 8, color: colors.accent, fontSize: font.xs }}>
                  — {c.image_refs.length} 张图片
                </span>
              )}
            </summary>
            <pre style={{
              whiteSpace: "pre-wrap", fontSize: font.xs, color: colors.text, margin: 0,
              padding: "12px 14px", lineHeight: 1.6,
            }}>{c.content.length > 500 ? c.content.slice(0, 500) + "..." : c.content}</pre>
            {c.image_refs.length > 0 && (
              <div style={{ padding: "0 14px 12px", display: "flex", gap: 6, flexWrap: "wrap" }}>
                {c.image_refs.map((ref) => (
                  <span key={ref.asset_id} style={{
                    display: "inline-block", fontSize: font.xs,
                    background: "#eff6ff", color: colors.accent, padding: "2px 8px", borderRadius: radius.sm,
                    border: "1px solid #bfdbfe",
                  }}>
                    {ref.filename} {ref.caption && `— ${ref.caption.slice(0, 40)}...`}
                  </span>
                ))}
              </div>
            )}
          </details>
        ))}
      </div>

      {/* Assets Section */}
      <div style={card}>
        <h3 style={{ margin: "0 0 14px 0", fontSize: font.md, fontWeight: 600, display: "flex", alignItems: "center", gap: 8 }}>
          图片资产
          <span style={{ fontSize: font.xs, color: colors.textMuted, fontWeight: 400 }}>({assets.length})</span>
        </h3>
        {assets.length === 0 && (
          <div style={{ color: colors.textMuted, fontSize: font.sm, textAlign: "center", padding: 32 }}>暂无图片资产</div>
        )}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 12 }}>
          {assets.map((a) => (
            <div key={a.id} style={{
              border: `1px solid ${colors.border}`, borderRadius: radius.md, padding: 14,
              background: colors.hover,
            }}>
              <div style={{ fontSize: font.sm, fontWeight: 600, marginBottom: 6, color: colors.text, wordBreak: "break-all" }}>{a.filename}</div>
              <div style={{ display: "flex", gap: 12, fontSize: font.xs, color: colors.textSecondary, marginBottom: 2 }}>
                <span>{a.content_type}</span>
                <span>{formatSize(a.size_bytes)}</span>
                {a.source_page && <span>第 {a.source_page} 页</span>}
              </div>
              {a.caption ? (
                <div style={{
                  fontSize: font.xs, color: colors.text, marginTop: 8, fontStyle: "italic",
                  background: colors.surface, padding: "8px 10px", borderRadius: radius.sm,
                  border: `1px solid ${colors.borderLight}`, lineHeight: 1.5,
                }}>{a.caption}</div>
              ) : (
                <div style={{ fontSize: font.xs, color: colors.textMuted, marginTop: 8 }}>无描述</div>
              )}
              {a.associated_chunks && a.associated_chunks.length > 0 && (
                <div style={{ marginTop: 8, fontSize: 10, color: colors.textMuted }}>
                  关联 chunks: {a.associated_chunks.join(", ")}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Job History */}
      <div style={card}>
        <h3 style={{ margin: "0 0 14px 0", fontSize: font.md, fontWeight: 600, display: "flex", alignItems: "center", gap: 8 }}>
          任务历史
          <span style={{ fontSize: font.xs, color: colors.textMuted, fontWeight: 400 }}>({jobs.length})</span>
        </h3>
        {jobs.length === 0 && (
          <div style={{ color: colors.textMuted, fontSize: font.sm, textAlign: "center", padding: 32 }}>暂无任务记录</div>
        )}
        {jobs.map((j) => (
          <div key={j.id} style={{
            display: "flex", alignItems: "center", gap: 14, padding: "10px 0",
            borderBottom: `1px solid ${colors.borderLight}`, fontSize: font.sm,
          }}>
            <span style={{ minWidth: 36, color: colors.textMuted, fontSize: font.xs }}>#{j.id}</span>
            <span style={{ minWidth: 80, fontWeight: 600 }}>{j.type}</span>
            <span style={{ minWidth: 72 }}><span style={badge(j.status)}>{j.status}</span></span>
            <span style={{ color: colors.textMuted, flex: 1, fontSize: font.xs }}>{new Date(j.created_at).toLocaleString()}</span>
            {j.error && <span style={{ color: colors.danger, fontSize: font.xs, maxWidth: 240, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{j.error}</span>}
          </div>
        ))}
      </div>
    </div>
  );
}

function Field({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div>
      <div style={{ fontSize: font.xs, color: colors.textMuted, marginBottom: 4, fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.3px" }}>{label}</div>
      <input value={value} onChange={(e) => onChange(e.target.value)}
        style={{ ...inputBase, width: "100%" }} />
    </div>
  );
}

function ReadOnly({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <div style={{ fontSize: font.xs, color: colors.textMuted, marginBottom: 4, fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.3px" }}>{label}</div>
      <div style={{ fontSize: font.sm, padding: "8px 0" }}>{value}</div>
    </div>
  );
}

function formatSize(bytes: number) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}
