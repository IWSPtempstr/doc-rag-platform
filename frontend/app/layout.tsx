export const metadata = { title: "文档 RAG 平台", description: "Document RAG Platform v2.0" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body style={{ margin: 0, fontFamily: "system-ui, sans-serif", background: "#f5f5f5" }}>
        <nav style={{ background: "#1a1a2e", color: "#fff", padding: "0 24px", display: "flex", gap: 24, height: 48, alignItems: "center" }}>
          <a href="/" style={{ color: "#fff", textDecoration: "none", fontWeight: 700 }}>RAG Platform v2.0</a>
          <a href="/documents" style={linkStyle}>文档</a>
          <a href="/chat" style={linkStyle}>问答</a>
          <a href="/settings" style={linkStyle}>设置</a>
          <a href="/health" style={linkStyle}>健康</a>
          <a href="/evaluations" style={linkStyle}>评估</a>
        </nav>
        <main style={{ maxWidth: 960, margin: "24px auto", padding: "0 16px" }}>{children}</main>
      </body>
    </html>
  );
}

const linkStyle: React.CSSProperties = { color: "#ccc", textDecoration: "none", fontSize: 14 };
