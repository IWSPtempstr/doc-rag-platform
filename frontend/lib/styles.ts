// Shared design tokens for the RAG Platform

export const colors = {
  bg: "#f5f5f7",
  surface: "#ffffff",
  dark: "#1a1a2e",
  primary: "#1a1a2e",
  accent: "#3b82f6",
  success: "#10b981",
  warn: "#f59e0b",
  danger: "#ef4444",
  text: "#1f2937",
  textSecondary: "#6b7280",
  textMuted: "#9ca3af",
  border: "#e5e7eb",
  borderLight: "#f3f4f6",
  selected: "#eff6ff",
  hover: "#f9fafb",
};

export const radius = { sm: 6, md: 8, lg: 12, xl: 16 };

export const shadow = {
  sm: "0 1px 2px rgba(0,0,0,0.05)",
  md: "0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.06)",
  lg: "0 4px 12px rgba(0,0,0,0.1)",
};

export const font = {
  xs: "11px",
  sm: "13px",
  base: "14px",
  md: "15px",
  lg: "18px",
  xl: "22px",
  xxl: "28px",
};

// ---- Shared Component Styles ----

export const card: React.CSSProperties = {
  background: colors.surface,
  borderRadius: radius.lg,
  padding: 20,
  marginBottom: 16,
  border: `1px solid ${colors.border}`,
  boxShadow: shadow.sm,
};

export const badge = (status: string): React.CSSProperties => {
  const map: Record<string, string> = {
    completed: colors.success,
    processing: colors.warn,
    pending: colors.textMuted,
    failed: colors.danger,
  };
  return {
    display: "inline-block",
    padding: "2px 10px",
    borderRadius: 12,
    fontSize: font.xs,
    fontWeight: 600,
    color: "#fff",
    background: map[status] || colors.textMuted,
  };
};

export const btnPrimary: React.CSSProperties = {
  background: colors.primary,
  color: "#fff",
  border: "none",
  padding: "8px 18px",
  borderRadius: radius.sm,
  cursor: "pointer",
  fontSize: font.sm,
  fontWeight: 600,
  transition: "opacity 0.15s",
};

export const btnDanger: React.CSSProperties = {
  background: colors.danger,
  color: "#fff",
  border: "none",
  padding: "6px 14px",
  borderRadius: radius.sm,
  cursor: "pointer",
  fontSize: font.xs,
  fontWeight: 600,
};

export const btnGhost: React.CSSProperties = {
  background: "transparent",
  color: colors.textSecondary,
  border: `1px solid ${colors.border}`,
  padding: "6px 14px",
  borderRadius: radius.sm,
  cursor: "pointer",
  fontSize: font.xs,
};

export const inputBase: React.CSSProperties = {
  padding: "8px 12px",
  borderRadius: radius.sm,
  border: `1px solid ${colors.border}`,
  fontSize: font.base,
  outline: "none",
  transition: "border-color 0.15s",
  boxSizing: "border-box",
  background: colors.surface,
};

export const titleStyle: React.CSSProperties = {
  fontSize: font.xxl,
  fontWeight: 700,
  color: colors.text,
  marginBottom: 24,
};

export const pageStyle: React.CSSProperties = {
  maxWidth: 1024,
  margin: "0 auto",
};
