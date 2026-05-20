"use client";

import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { useRouter, usePathname } from "next/navigation";
import { api } from "@/lib/api";

interface User {
  id: number;
  email: string;
  name: string;
  is_active: boolean;
}

interface Workspace {
  id: number;
  name: string;
  slug: string;
}

interface AuthState {
  user: User | null;
  workspaces: Workspace[];
  loading: boolean;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState>({
  user: null,
  workspaces: [],
  loading: true,
  logout: async () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  const checkAuth = useCallback(async () => {
    try {
      const data: any = await api.me();
      setUser(data.user);
      setWorkspaces(data.workspaces || []);
    } catch {
      setUser(null);
      setWorkspaces([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { checkAuth(); }, [checkAuth]);

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } catch {}
    setUser(null);
    setWorkspaces([]);
    router.push("/login");
  }, [router]);

  return (
    <AuthContext.Provider value={{ user, workspaces, loading, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!loading && !user) {
      router.push(`/login?redirect=${encodeURIComponent(pathname)}`);
    }
  }, [loading, user, router, pathname]);

  if (loading) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: 200 }}>
        <span style={{ color: "#9ca3af", fontSize: 14 }}>检查登录状态...</span>
      </div>
    );
  }

  if (!user) return null;
  return <>{children}</>;
}
