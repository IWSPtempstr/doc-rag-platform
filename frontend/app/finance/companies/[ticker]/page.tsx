"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { ProtectedRoute } from "@/lib/auth";
import type { Filing, FilingSection } from "@/lib/types";
import { colors, font, card, btnGhost, btnPrimary } from "@/lib/styles";

export default function FinanceCompanyPage() {
  return <ProtectedRoute><FinanceCompanyPageInner /></ProtectedRoute>;
}

function FinanceCompanyPageInner() {
  const params = useParams();
  const router = useRouter();
  const ticker = String(params.ticker || "").toUpperCase();
  const [company, setCompany] = useState<any>(null);
  const [filings, setFilings] = useState<Filing[]>([]);
  const [sections, setSections] = useState<Record<number, FilingSection[]>>({});
  const [message, setMessage] = useState("");

  const load = () => {
    api.getCompany(ticker).then((data: any) => {
      setCompany(data.company);
      setFilings(data.filings || []);
      (data.filings || []).forEach((filing: Filing) => {
        api.getFilingSections(filing.id).then((rows: any) => {
          setSections((prev) => ({ ...prev, [filing.id]: rows }));
        }).catch(() => {});
      });
    }).catch(console.error);
  };

  useEffect(() => { load(); }, [ticker]);

  const importLatest = async () => {
    try {
      const filing: any = await api.importFiling(ticker, {});
      setMessage(`${filing.fiscal_year} 10-K 已加入导入队列`);
      load();
    } catch (err: any) {
      setMessage(`导入失败: ${err.message}`);
    }
  };

  if (!company) return <div style={card}>加载中...</div>;

  return (
    <div>
      <a onClick={() => router.push("/finance")} style={{ color: colors.accent, cursor: "pointer", fontSize: font.sm }}>
        &larr; 返回财报工作台
      </a>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", margin: "12px 0 20px" }}>
        <div>
          <h1 style={{ margin: 0, fontSize: font.xxl }}>{company.ticker} · {company.name}</h1>
          <p style={{ margin: "6px 0 0", color: colors.textSecondary, fontSize: font.sm }}>CIK: {company.cik || "-"}</p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button style={btnGhost} onClick={() => router.push(`/finance/agent?ticker=${company.ticker}`)}>Agent 分析</button>
          <button style={btnPrimary} onClick={importLatest}>导入最新 10-K</button>
        </div>
      </div>

      {message && <div style={{ ...card, color: message.includes("失败") ? colors.danger : colors.success, padding: 12 }}>{message}</div>}

      <div style={card}>
        <h2 style={{ margin: "0 0 14px", fontSize: font.lg }}>10-K Filings</h2>
        {filings.length === 0 ? (
          <div style={{ color: colors.textMuted, padding: 24, textAlign: "center" }}>暂无 10-K，点击导入。</div>
        ) : filings.map((filing) => (
          <div key={filing.id} style={{ border: `1px solid ${colors.border}`, borderRadius: 8, padding: 14, marginBottom: 12 }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
              <div>
                <strong>{filing.filing_type} · FY {filing.fiscal_year}</strong>
                <div style={{ color: colors.textSecondary, fontSize: font.xs, marginTop: 4 }}>
                  {filing.accession_number || "local filing"} · {filing.status}
                </div>
                {filing.document && (
                  <div style={{ color: colors.textSecondary, fontSize: font.xs, marginTop: 4 }}>
                    文档: {filing.document.filename} · {filing.document.status} · chunks {filing.document.chunk_count}
                  </div>
                )}
              </div>
              <div>
                {filing.document_id && (
                  <button style={btnGhost} onClick={() => router.push(`/documents/${filing.document_id}`)}>文档详情</button>
                )}
              </div>
            </div>

            <div style={{ marginTop: 12, display: "grid", gap: 8 }}>
              {(sections[filing.id] || []).slice(0, 6).map((section) => (
                <details key={section.id} style={{ background: colors.hover, borderRadius: 6, padding: "8px 10px" }}>
                  <summary style={{ cursor: "pointer", fontSize: font.sm, fontWeight: 600 }}>
                    Item {section.item_code} · {section.title}
                  </summary>
                  <p style={{ whiteSpace: "pre-wrap", fontSize: font.xs, lineHeight: 1.6 }}>{section.content_preview}</p>
                </details>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

