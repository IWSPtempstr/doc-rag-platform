export interface Document {
  id: number;
  filename: string;
  content_type: string;
  size_bytes: number;
  status: string;
  tags: string;
  chunk_count: number;
  image_count: number;
  has_images: boolean;
  kb_version: number;
  created_at: string;
  updated_at: string | null;
  latest_job: {
    id: number;
    type: string;
    status: string;
    error: string | null;
  } | null;
}

export interface DocumentChunk {
  chunk_id: string;
  document_id: number;
  filename: string;
  content: string;
  metadata: Record<string, any>;
  image_refs: ImageRef[];
}

export interface ImageRef {
  asset_id: number;
  filename: string;
  caption: string | null;
  source_page: number | null;
}

export interface ImageAsset {
  id: number;
  document_id: number;
  filename: string;
  source_page: number | null;
  content_type: string;
  size_bytes: number;
  caption: string | null;
  caption_model: string | null;
  associated_chunks: string[] | null;
  created_at: string;
}

export interface Job {
  id: number;
  document_id: number;
  type: string;
  status: string;
  error: string | null;
  retry_count: number;
  created_at: string;
  updated_at: string | null;
  progress: { stage: string; message: string } | null;
}

export interface ReindexResponse {
  document_id: number;
  job_id: number;
  message: string;
}

export interface Settings {
  provider: string;
  chat_provider: string;
  embedding_provider: string;
  chat_model: string;
  embed_model: string;
  top_k: number;
  stream: boolean;
  vision_provider: string;
  vision_model: string;
}

export interface Health {
  status: string;
  sqlite: string;
  redis: string;
  chroma: string;
  provider: string;
  chat_provider: string;
  embedding_provider: string;
  redis_queue_length: number;
}

export interface ChatQueryResult {
  answer: string;
  citations: Citation[];
  model: string;
  provider: string;
  chat_provider: string;
  embedding_provider: string;
  embedding_model: string;
  cache_hit: boolean;
  session_id: number | null;
}

export interface Citation {
  chunk_id: string;
  document_id: number;
  filename: string;
  content: string;
  score: number;
}

export interface ChatSession {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
  messages: { role: string; content: string; citations?: any; cache_hit?: boolean }[];
}

export interface Company {
  id: number;
  workspace_id: number;
  ticker: string;
  name: string;
  cik: string | null;
  exchange: string | null;
  industry: string | null;
  created_at: string;
  updated_at: string | null;
  filing_count: number;
}

export interface CompanyCoverage {
  company_id: number;
  ticker: string;
  document_count: number;
  filing_count: number;
  chunk_count: number;
  chroma_chunk_count: number;
  section_count: number;
  financial_fact_count: number;
  market_fact_count: number;
  indexed_document_count: number;
  failure_flags: string[];
  filings: Array<{
    id: number;
    filing_type: string;
    fiscal_year: number;
    status: string;
    document_id: number | null;
    metadata_json: Record<string, any> | null;
  }>;
}

export interface CompanyResearchSummary {
  company: {
    id: number;
    ticker: string;
    name: string;
    market: string | null;
    industry: string | null;
    watchlisted: boolean;
  };
  available_signals: Record<string, any>;
  missing_items: string[];
  failure_reasons: Record<string, string>;
  can_infer: string[];
  cannot_infer: string[];
  next_actions: Array<{ key: string; label: string; priority: number }>;
  analysis_boundary: string[];
  coverage_tags: string[];
  generated_at: string;
}

export interface Filing {
  id: number;
  workspace_id: number;
  company_id: number;
  document_id: number | null;
  accession_number: string | null;
  filing_type: string;
  fiscal_year: number;
  filed_at: string | null;
  source_url: string | null;
  status: string;
  metadata_json: Record<string, any> | null;
  created_at: string;
  updated_at: string | null;
  company?: { id: number; ticker: string; name: string; cik: string | null };
  document?: { id: number; filename: string; status: string; chunk_count: number };
}

export interface FilingSection {
  id: number;
  filing_id: number;
  item_code: string;
  title: string;
  content_preview: string | null;
  char_start: number;
  char_end: number;
  created_at: string;
}

export interface FinanceAgentResult {
  answer: string;
  citations: any[];
  facts: any[];
  calculations: any[];
  agent_run_id: number;
  steps: any[];
  verification: Record<string, any>;
}

export interface AgentRunSummary {
  id: number;
  company_id?: number | null;
  company?: { id: number; ticker: string; name: string } | null;
  filing_id: number | null;
  question: string;
  mode: string;
  status: string;
  answer_preview: string;
  verification: Record<string, any>;
  created_at: string;
  completed_at: string | null;
}

export interface ConnectorStatusRow {
  name: string;
  label: string;
  category: string;
  source: string;
  capabilities: string[];
  status: string;
  failure_reason: string | null;
  last_sync_at: string | null;
  coverage: Record<string, any>;
}

export interface ConnectorStatusResponse {
  connectors: ConnectorStatusRow[];
  daily_jobs: Array<{
    name: string;
    source: string;
    schedule: string;
    status: string;
    last_run_at: string | null;
    next_run_at: string | null;
    failure_reason: string | null;
  }>;
}

export interface WatchlistItem {
  id: number;
  user_id: number;
  workspace_id: number;
  ticker: string;
  priority: number;
  created_at: string;
  company: { id: number; ticker: string; name: string } | null;
}

export interface DailyBrief {
  trade_date: string;
  status: string;
  summary: string | null;
  items: Array<Record<string, any>>;
  metadata: Record<string, any>;
}

export interface SentimentFact {
  id: number;
  workspace_id: number;
  ticker: string | null;
  trade_date: string;
  scope: string;
  score: number | null;
  label: string | null;
  source: string;
  evidence: string | null;
  metadata_json: Record<string, any> | null;
  created_at: string;
}

export interface FinanceEvalResult {
  id: number;
  workspace_id: number;
  dataset_id: number | null;
  strategy: string;
  metrics: Record<string, any> | null;
  results: any;
  created_at: string;
}

export interface FinanceAlert {
  type: string;
  alert_type: string;
  source: string;
  dataset_name: string | null;
  result_id: number | null;
  run_id: number | null;
  metric_value: number;
  threshold: number;
  direction: string;
  severity: string;
  created_at: string;
  message: string;
}

export interface FinanceEvalJsonlExport {
  dataset_id: number;
  dataset_name: string;
  file_path: string;
  case_count: number;
}

export interface EvalDataset {
  id: number;
  workspace_id: number;
  name: string;
  source: string;
  version: string;
  description: string | null;
  manifest_json: Record<string, any> | null;
  case_count: number;
  frozen_at: string | null;
  source_url: string | null;
  license_note: string | null;
  created_at: string;
}

export interface EvalCase {
  id: number;
  dataset_id: number;
  case_uid: string | null;
  question: string;
  expected_answer: string | null;
  expected_evidence: any;
  expected_numeric: number | null;
  expected_calculation: any;
  tolerance: number;
  task_type: string | null;
  difficulty: string;
  status: string;
  gold_filing_id: number | null;
  gold_document_id: number | null;
  rubric_json: any;
  metadata_json: any;
  created_at: string;
}

export interface FinanceSummary {
  company_count: number;
  filing_count: number;
  dataset_count: number;
  frozen_dataset_count: number;
  case_count: number;
  latest_eval: Record<string, any> | null;
  dataset_failure_counts: Record<string, number>;
  datasets: Array<{
    id: number;
    name: string;
    source: string;
    version: string;
    case_count: number;
    frozen_at: string | null;
    source_url: string | null;
    license_note: string | null;
    public_data_only: boolean;
  }>;
}

export interface FinancialFact {
  id: number;
  filing_id: number;
  metric: string;
  label: string;
  value: number | null;
  unit: string | null;
  period: string | null;
  source: string;
  evidence: string | null;
  confidence: number | null;
  created_at: string;
}

export interface MarketFact {
  id: number;
  workspace_id: number;
  company_id: number;
  ticker: string;
  trade_date: string;
  metric: string;
  label: string;
  value: number | null;
  unit: string | null;
  source: string;
  source_url: string | null;
  confidence: number | null;
  metadata_json: Record<string, any> | null;
  created_at: string | null;
}
