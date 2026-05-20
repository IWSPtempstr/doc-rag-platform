"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { colors, font, card, inputBase, btnPrimary } from "@/lib/styles";

export default function LoginPage() {
  return <Suspense><LoginPageInner /></Suspense>;
}

function LoginPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const redirect = searchParams.get("redirect") || "/finance";
  const [email, setEmail] = useState("admin@example.com");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");

  const login = async () => {
    try {
      await api.login(email, password, "Admin");
      router.push(redirect);
    } catch (err: any) {
      setMessage(err.message);
    }
  };

  return (
    <div style={{ maxWidth: 420, margin: "80px auto" }}>
      <div style={{ ...card, padding: 28 }}>
        <h1 style={{ margin: "0 0 6px", fontSize: font.xl }}>登录财报工作台</h1>
        <p style={{ margin: "0 0 18px", color: colors.textSecondary, fontSize: font.sm }}>
          首次登录会创建本机管理员账号和默认工作空间。
        </p>
        <div style={{ marginBottom: 14 }}>
          <label style={label}>邮箱</label>
          <input value={email} onChange={(e) => setEmail(e.target.value)} style={{ ...inputBase, width: "100%" }} />
        </div>
        <div style={{ marginBottom: 14 }}>
          <label style={label}>密码</label>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} style={{ ...inputBase, width: "100%" }} />
        </div>
        <button onClick={login} style={{ ...btnPrimary, width: "100%" }}>登录</button>
        {message && <div style={{ color: colors.danger, marginTop: 12, fontSize: font.sm }}>{message}</div>}
      </div>
    </div>
  );
}
const label: React.CSSProperties = {
  display: "block",
  color: colors.textSecondary,
  fontSize: font.xs,
  fontWeight: 600,
  marginBottom: 5,
};

