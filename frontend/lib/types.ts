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

export interface FinanceEvalResult {
  id: number;
  workspace_id: number;
  dataset_id: number | null;
  strategy: string;
  metrics: Record<string, any> | null;
  results: any;
  created_at: string;
}
