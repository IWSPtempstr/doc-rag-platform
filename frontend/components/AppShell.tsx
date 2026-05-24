"use client";

import { useAuth } from "@/lib/auth";

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, workspaces, logout } = useAuth();
  const role = workspaces[0]?.role || "user";
  const isAdmin = role === "admin" || role === "owner";
  const navItems: Array<{ href: string; label: string; visible: boolean }> = [
    { href: "/finance", label: "每日简报", visible: true },
    { href: "/documents", label: "公告资产", visible: true },
    { href: "/finance/agent", label: "个性化分析", visible: true },
    { href: "/finance/connectors", label: "数据源管理", visible: isAdmin },
    { href: "/finance/evaluations", label: "评估管理", visible: isAdmin },
    { href: "/settings", label: "设置", visible: isAdmin },
    { href: "/health", label: "健康", visible: isAdmin },
  ];

  return (
    <>
      <nav style={{
        background: "#1a1a2e", color: "#fff", padding: "0 28px", display: "flex", gap: 28, height: 52,
        alignItems: "center", position: "sticky", top: 0, zIndex: 100, boxShadow: "0 1px 4px rgba(0,0,0,0.15)",
      }}>
        <a href="/" style={{ color: "#fff", textDecoration: "none", fontWeight: 700, fontSize: 15, letterSpacing: "-0.3px" }}>
          A 股公告与情绪分析工作台
        </a>
        {navItems.filter((item) => item.visible).map((item) => (
          <a key={item.href} href={item.href} style={navLinkStyle}>{item.label}</a>
        ))}
        <div style={{ flex: 1 }} />
        {user ? (
          <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
            <span style={{ fontSize: 12, color: "#9ca3af" }}>{user.name || user.email} · {role}</span>
            <button onClick={logout} style={{
              background: "transparent", color: "#9ca3af", border: "1px solid #4b5563",
              padding: "4px 12px", borderRadius: 4, cursor: "pointer", fontSize: 12,
            }}>登出</button>
          </div>
        ) : (
          <a href="/login" style={{ ...navLinkStyle, color: "#60a5fa" }}>登录</a>
        )}
      </nav>
      <main style={{ maxWidth: 1040, margin: "28px auto", padding: "0 20px" }}>{children}</main>
    </>
  );
}

const navLinkStyle: React.CSSProperties = {
  color: "#9ca3af", textDecoration: "none", fontSize: 13, fontWeight: 500,
  padding: "4px 0", borderBottom: "2px solid transparent", transition: "color 0.15s, border-color 0.15s",
};
