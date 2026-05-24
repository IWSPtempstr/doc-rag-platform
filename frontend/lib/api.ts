const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail?.message || err.detail || res.statusText);
  }
  return res.json();
}

export const api = {
  // Documents
  uploadDocument: (formData: FormData) =>
    request("/documents/upload", { method: "POST", body: formData, headers: {} }),
  listDocuments: (params?: {
    tag?: string; status?: string; search?: string;
    has_images?: boolean; offset?: number; limit?: number;
  }) => {
    const qs = new URLSearchParams();
    if (params) {
      Object.entries(params).forEach(([k, v]) => {
        if (v !== undefined && v !== "" && v !== null) qs.set(k, String(v));
      });
    }
    const q = qs.toString();
    return request(`/documents${q ? `?${q}` : ""}`);
  },
  getDocument: (id: number) => request(`/documents/${id}`),
  updateDocument: (id: number, data: object) =>
    request(`/documents/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteDocument: (id: number) =>
    request(`/documents/${id}`, { method: "DELETE" }),
  getDocumentChunks: (id: number) => request(`/documents/${id}/chunks`),
  getDocumentAssets: (id: number) => request(`/documents/${id}/assets`),
  getDocumentJobs: (id: number) => request(`/documents/${id}/jobs`),
  reindexDocument: (id: number) =>
    request(`/documents/${id}/reindex`, { method: "POST" }),

  // Jobs
  getJob: (id: number) => request(`/jobs/${id}`),

  // Chat
  query: (question: string, top_k?: number) =>
    request("/chat/query", { method: "POST", body: JSON.stringify({ question, top_k }) }),
  listSessions: () => request("/chat/sessions"),
  getSession: (id: number) => request(`/chat/sessions/${id}`),

  // Settings
  getSettings: () => request("/settings/provider"),
  updateSettings: (data: object) =>
    request("/settings/provider", { method: "POST", body: JSON.stringify(data) }),

  // Health
  getHealth: () => request("/health"),

  // Traces
  getIngestionTraces: (limit?: number) => request(`/traces/ingestion?limit=${limit || 50}`),
  getQueryTraces: (limit?: number) => request(`/traces/query?limit=${limit || 50}`),

  // Evaluations
  runEvaluation: (strategy?: string) =>
    request("/evaluations/run", { method: "POST", body: JSON.stringify({ strategy: strategy || "dense" }) }),
  getEvaluationResults: () => request("/evaluations/results"),

  // Collections
  listCollections: () => request("/collections"),

  // Auth
  login: (email: string, password: string, name?: string) =>
    request("/auth/login", { method: "POST", body: JSON.stringify({ email, password, name }) }),
  logout: () => request("/auth/logout", { method: "POST" }),
  me: () => request("/auth/me"),

  // Finance
  listCompanies: (workspace_id?: number) => {
    const qs = workspace_id ? `?workspace_id=${workspace_id}` : "";
    return request(`/finance/companies${qs}`);
  },
  createCompany: (data: object) =>
    request("/finance/companies", { method: "POST", body: JSON.stringify(data) }),
  getCompany: (ticker: string, workspace_id?: number) => {
    const qs = workspace_id ? `?workspace_id=${workspace_id}` : "";
    return request(`/finance/companies/${encodeURIComponent(ticker)}${qs}`);
  },
  deleteCompany: (ticker: string) =>
    request(`/finance/companies/${encodeURIComponent(ticker)}`, { method: "DELETE" }),
  getCompanyCoverage: (ticker: string) =>
    request(`/finance/companies/${encodeURIComponent(ticker)}/coverage`),
  getCompanyResearchSummary: (ticker: string) =>
    request(`/finance/companies/${encodeURIComponent(ticker)}/research-summary`),
  getWatchlist: () => request("/finance/watchlist"),
  addWatchlist: (data: object) =>
    request("/finance/watchlist", { method: "POST", body: JSON.stringify(data) }),
  removeWatchlist: (ticker: string) =>
    request(`/finance/watchlist/${encodeURIComponent(ticker)}`, { method: "DELETE" }),
  getDailyBrief: (date?: string) =>
    request(`/finance/daily-brief${date ? `?date=${encodeURIComponent(date)}` : ""}`),
  getSentimentFacts: (params?: { ticker?: string; limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.ticker) qs.set("ticker", params.ticker);
    if (params?.limit) qs.set("limit", String(params.limit));
    const q = qs.toString();
    return request(`/finance/sentiment${q ? `?${q}` : ""}`);
  },
  syncSentiment: () =>
    request("/admin/finance/jobs/daily-sync/run", { method: "POST" }),
  listCompanyAgentRuns: (ticker: string, limit?: number) => {
    const qs = limit ? `?limit=${limit}` : "";
    return request(`/finance/companies/${encodeURIComponent(ticker)}/agent-runs${qs}`);
  },
  listFinanceAgentRuns: (params?: { company_ticker?: string; limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.company_ticker) qs.set("company_ticker", params.company_ticker);
    if (params?.limit) qs.set("limit", String(params.limit));
    const q = qs.toString();
    return request(`/finance/agent/runs${q ? `?${q}` : ""}`);
  },
  deleteFinanceAgentRun: (runId: number) =>
    request(`/finance/agent/runs/${runId}`, { method: "DELETE" }),
  importFiling: (ticker: string, data: object) =>
    request(`/finance/companies/${encodeURIComponent(ticker)}/filings/import`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  listAshareAnnouncements: (ticker: string, params?: Record<string, string | number | undefined>) => {
    const qs = new URLSearchParams();
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") qs.set(k, String(v));
    });
    const q = qs.toString();
    return request(`/finance/ashare/companies/${encodeURIComponent(ticker)}/announcements${q ? `?${q}` : ""}`);
  },
  importAshareFiling: (ticker: string, data: object) =>
    request(`/finance/ashare/companies/${encodeURIComponent(ticker)}/filings/import`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  syncAshareFacts: (ticker: string, data?: object) =>
    request(`/finance/ashare/companies/${encodeURIComponent(ticker)}/facts/sync`, {
      method: "POST",
      body: JSON.stringify(data || {}),
    }),
  syncAshareMarket: (ticker: string, data?: object) =>
    request(`/finance/ashare/companies/${encodeURIComponent(ticker)}/market/sync`, {
      method: "POST",
      body: JSON.stringify(data || {}),
    }),
  getFilingFacts: (id: number) => request(`/finance/filings/${id}/facts`),
  getMarketFacts: (ticker: string) => request(`/finance/companies/${encodeURIComponent(ticker)}/market-facts`),
  getFiling: (id: number) => request(`/finance/filings/${id}`),
  deleteFiling: (id: number) =>
    request(`/finance/filings/${id}`, { method: "DELETE" }),
  getFilingSections: (id: number) => request(`/finance/filings/${id}/sections`),
  bindFilingDocument: (id: number, data: object) =>
    request(`/finance/filings/${id}/bind-document`, { method: "POST", body: JSON.stringify(data) }),
  queryFinanceAgent: (data: object) =>
    request("/finance/agent/query", { method: "POST", body: JSON.stringify(data) }),
  getFinanceAgentTrace: (runId: number) =>
    request(`/finance/agent/runs/${runId}/trace`),
  runFinanceEvaluation: (data: object) =>
    request("/finance/evaluations/run", { method: "POST", body: JSON.stringify(data) }),
  listFinanceEvaluationResults: (workspace_id?: number) => {
    const qs = workspace_id ? `?workspace_id=${workspace_id}` : "";
    return request(`/finance/evaluations/results${qs}`);
  },
  importFinanceEvalJsonl: (data: object) =>
    request("/finance/evaluations/import-jsonl", { method: "POST", body: JSON.stringify(data) }),
  exportFinanceEvalJsonl: (datasetName: string) =>
    request(`/finance/evaluations/export-jsonl?dataset_name=${encodeURIComponent(datasetName)}`),
  getFinanceAlerts: (limit?: number) =>
    request(`/finance/observability/alerts?limit=${limit || 50}`),
  getFinanceSummary: () => request("/finance/summary"),

  // Finance Datasets
  listDatasets: () => request("/finance/datasets"),
  getDatasetCases: (datasetId: number, status?: string, taskType?: string) => {
    const params = new URLSearchParams();
    if (status) params.set("status", status);
    if (taskType) params.set("task_type", taskType);
    const qs = params.toString();
    return request(`/finance/datasets/${datasetId}/cases${qs ? `?${qs}` : ""}`);
  },
  updateEvalCase: (caseId: number, data: object) =>
    request(`/finance/eval-cases/${caseId}`, { method: "PATCH", body: JSON.stringify(data) }),
  freezeDataset: (datasetId: number) =>
    request(`/finance/datasets/${datasetId}/freeze`, { method: "POST" }),

  // Finance Admin
  getAdminConnectorStatus: () => request("/admin/finance/connectors/status"),
  testAdminConnector: (name: string) =>
    request(`/admin/finance/connectors/${encodeURIComponent(name)}/test`, { method: "POST" }),
  runAdminDailySync: (date?: string) =>
    request(`/admin/finance/jobs/daily-sync/run${date ? `?date=${encodeURIComponent(date)}` : ""}`, { method: "POST" }),
  getAdminDailySyncHistory: (limit?: number) =>
    request(`/admin/finance/jobs/daily-sync/history?limit=${limit || 30}`),
  getAdminEvaluationResults: (limit?: number) =>
    request(`/admin/finance/evaluations/results?limit=${limit || 30}`),
};
