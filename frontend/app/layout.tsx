import { AuthProvider } from "@/lib/auth";
import { AppShell } from "@/components/AppShell";

export const metadata = { title: "财报分析工作台", description: "Financial RAG Workbench" };

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
