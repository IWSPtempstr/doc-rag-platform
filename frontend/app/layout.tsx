import { AuthProvider } from "@/lib/auth";
import { AppShell } from "@/components/AppShell";

export const metadata = { title: "文档 RAG 平台", description: "Document RAG Platform v3.0" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body style={{ margin: 0, fontFamily: "'Inter Display', system-ui, -apple-system, sans-serif", background: "#f5f5f7", color: "#1f2937" }}>
        <AuthProvider>
          <AppShell>{children}</AppShell>
        </AuthProvider>
      </body>
    </html>
  );
}
