"use client";

import { useAuth } from "@/lib/auth";
import Link from "next/link";

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth();

  return (
    <>
      <nav style={{
        background: "#1a1a2e", color: "#fff", padding: "0 28px", display: "flex", gap: 28, height: 52,
        alignItems: "center", position: "sticky", top: 0, zIndex: 100, boxShadow: "0 1px 4px rgba(0,0,0,0.15)",
      }}>
        <a href="/" style={{ color: "#fff", textDecoration: "none", fontWeight: 700, fontSize: 15, letterSpacing: "-0.3px" }}>
          财报分析工作台
        </a>
        {[
          ["/finance", "财报"],
          ["/finance/connectors", "数据源"],
          ["/documents", "资产"],
          ["/finance/agent", "Agent"],
          ["/finance/evaluations", "评估"],
          ["/settings", "设置"],
          ["/health", "健康"],
        ].map(([href, label]) => (
          <a key={href} href={href} style={navLinkStyle}>{label}</a>
        ))}
        <div style={{ flex: 1 }} />
        {user ? (
          <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
            <span style={{ fontSize: 12, color: "#9ca3af" }}>{user.name || user.email}</span>
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
