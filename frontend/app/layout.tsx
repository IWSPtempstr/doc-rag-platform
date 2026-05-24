import { AuthProvider } from "@/lib/auth";
import { AppShell } from "@/components/AppShell";

export const metadata = { title: "A 股公告与情绪分析工作台", description: "A-share disclosure and sentiment workbench" };

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
