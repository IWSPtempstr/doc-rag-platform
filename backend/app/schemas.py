"""Pydantic Schema — API 输入输出"""

from datetime import datetime
from typing import Optional, Any, Literal
from pydantic import BaseModel, Field


# ---- Document ----
class DocumentResponse(BaseModel):
    id: int
    filename: str
    content_type: str
    size_bytes: int
    status: str
    tags: str
    chunk_count: int
    image_count: int = 0
    has_images: bool = False
    kb_version: int = 1
    created_at: datetime
    updated_at: Optional[datetime] = None
    latest_job: Optional[dict] = None

    model_config = {"from_attributes": True}


class DocumentUpdate(BaseModel):
    filename: Optional[str] = None
    tags: Optional[str] = None


class DocumentChunkResponse(BaseModel):
    chunk_id: str
    document_id: int
    filename: str
    content: str
    metadata: dict
    image_refs: list[dict] = []


# ---- Job ----
class JobResponse(BaseModel):
    id: int
    document_id: int
    type: str
    status: str
    error: Optional[str] = None
    retry_count: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    progress: Optional[dict] = None  # from Redis

    model_config = {"from_attributes": True}


# ---- Chat ----
class ChatQueryRequest(BaseModel):
    question: str = Field(..., min_length=1)
    top_k: Optional[int] = None
    collection: Optional[str] = None


class Citation(BaseModel):
    chunk_id: str
    document_id: int
    filename: str
    content: str
    score: float


class ChatQueryResponse(BaseModel):
    answer: str
    citations: list[Citation] = []
    model: str
    provider: str  # legacy alias for chat_provider
    chat_provider: str = "openai"
    embedding_provider: str = "ollama"
    embedding_model: str = "nomic-embed-text"
    cache_hit: bool
    session_id: Optional[int] = None


class ChatSessionResponse(BaseModel):
    id: int
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list[dict] = []

    model_config = {"from_attributes": True}


# ---- Settings ----
class ProviderSettingsRequest(BaseModel):
    provider: Optional[str] = None  # legacy alias for chat_provider
    chat_provider: Optional[str] = None
    embedding_provider: Optional[str] = None
    chat_model: Optional[str] = None
    embed_model: Optional[str] = None
    top_k: Optional[int] = None
    stream: Optional[bool] = None
    vision_provider: Optional[str] = None
    vision_model: Optional[str] = None


class SettingsResponse(BaseModel):
    provider: str  # legacy alias for chat_provider
    chat_provider: str
    embedding_provider: str
    chat_model: str
    embed_model: str
    top_k: int
    stream: bool
    vision_provider: str = "openai"
    vision_model: str = "deepseek-v4-pro"

    model_config = {"from_attributes": True}


# ---- Health ----
class HealthResponse(BaseModel):
    status: str  # ok / degraded / down
    sqlite: str
    redis: str
    chroma: str
    provider: str  # aggregate provider status
    chat_provider: str = "unknown"
    embedding_provider: str = "unknown"
    redis_queue_length: int = 0


# ---- Upload ----
class UploadResponse(BaseModel):
    document_id: int
    job_id: int
    filename: str
    content_type: str
    size_bytes: int
    is_image: bool = False


class ReindexResponse(BaseModel):
    document_id: int
    job_id: int
    message: str


class ImageAssetResponse(BaseModel):
    id: int
    document_id: int
    filename: str
    source_page: Optional[int] = None
    content_type: str
    size_bytes: int
    caption: Optional[str] = None
    caption_model: Optional[str] = None
    associated_chunks: Optional[list[str]] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---- Collection (v1.1) ----
class CollectionResponse(BaseModel):
    id: int
    name: str
    description: str
    document_count: int

    model_config = {"from_attributes": True}


# ---- Trace (v1.1) ----
class TraceEvent(BaseModel):
    stage: str
    timestamp: str
    duration_ms: float
    metadata: dict = {}


# ---- Evaluation (v1.1) ----
class EvaluationRunRequest(BaseModel):
    strategy: str = "dense"  # dense / hybrid / hybrid_rerank


class EvaluationResultResponse(BaseModel):
    id: int
    strategy: str
    hit_rate: Optional[float] = None
    context_precision: Optional[float] = None
    faithfulness: Optional[float] = None
    answer_relevancy: Optional[float] = None
    results: Optional[Any] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---- Auth / Workspace ----
class LoginRequest(BaseModel):
    email: str
    password: str
    name: Optional[str] = None


class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class WorkspaceResponse(BaseModel):
    id: int
    name: str
    slug: str
    created_at: datetime
    role: Optional[str] = None

    model_config = {"from_attributes": True}


class MeResponse(BaseModel):
    user: UserResponse
    workspaces: list[WorkspaceResponse] = []


# ---- Finance ----
class CompanyCreateRequest(BaseModel):
    workspace_id: int = 1
    ticker: str
    name: Optional[str] = None
    cik: Optional[str] = None
    exchange: Optional[str] = None
    industry: Optional[str] = None


class CompanyResponse(BaseModel):
    id: int
    workspace_id: int
    ticker: str
    name: str
    cik: Optional[str] = None
    exchange: Optional[str] = None
    industry: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    filing_count: int = 0

    model_config = {"from_attributes": True}


class FilingBindDocumentRequest(BaseModel):
    document_id: int
    fiscal_year: int
    filing_type: str = "annual_report"


class FilingResponse(BaseModel):
    id: int
    workspace_id: int
    company_id: int
    document_id: Optional[int] = None
    accession_number: Optional[str] = None
    filing_type: str
    fiscal_year: int
    filed_at: Optional[datetime] = None
    source_url: Optional[str] = None
    status: str
    metadata_json: Optional[dict] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    company: Optional[dict] = None
    document: Optional[dict] = None

    model_config = {"from_attributes": True}


class FilingSectionResponse(BaseModel):
    id: int
    filing_id: int
    item_code: str
    title: str
    content_preview: Optional[str] = None
    char_start: int
    char_end: int
    created_at: datetime

    model_config = {"from_attributes": True}


class FinancialFactResponse(BaseModel):
    id: int
    filing_id: int
    metric: str
    label: str
    value: Optional[float] = None
    unit: Optional[str] = None
    period: Optional[str] = None
    source: str
    evidence: Optional[str] = None
    confidence: Optional[float] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AshareAnnouncementResponse(BaseModel):
    market: str = "CN"
    source: str = "cninfo"
    ticker: str
    stock_code: str
    company_name: str
    exchange: str
    announcement_id: str
    announcement_title: str
    published_at: Optional[datetime] = None
    download_url: Optional[str] = None
    disclosure_category: Optional[str] = None
    filing_type: str
    fiscal_year: int


class AshareFilingImportRequest(BaseModel):
    fiscal_year: int
    announcement_id: Optional[str] = None
    keyword: Optional[str] = None


class AshareFactsSyncRequest(BaseModel):
    fiscal_year: Optional[int] = None
    provider: str = "akshare"


class AshareMarketSyncRequest(BaseModel):
    trade_date: Optional[str] = None
    provider: str = "akshare"


class MarketFactResponse(BaseModel):
    id: int
    workspace_id: int
    company_id: int
    ticker: str
    trade_date: str
    metric: str
    label: str
    value: Optional[float] = None
    unit: Optional[str] = None
    source: str
    source_url: Optional[str] = None
    confidence: Optional[float] = None
    metadata_json: Optional[dict] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class WatchlistCreateRequest(BaseModel):
    ticker: str
    priority: int = 100


class WatchlistResponse(BaseModel):
    id: int
    user_id: int
    workspace_id: int
    ticker: str
    priority: int
    created_at: datetime
    company: Optional[dict] = None

    model_config = {"from_attributes": True}


class SentimentFactResponse(BaseModel):
    id: int
    workspace_id: int
    ticker: Optional[str] = None
    trade_date: str
    scope: str
    score: Optional[float] = None
    label: Optional[str] = None
    source: str
    evidence: Optional[str] = None
    metadata_json: Optional[dict] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DailyBriefResponse(BaseModel):
    trade_date: str
    status: str
    summary: Optional[str] = None
    items: list[dict] = []
    metadata: dict = {}


class FinanceAgentQueryRequest(BaseModel):
    workspace_id: int = 1
    company_ticker: str
    filing_id: Optional[int] = None
    question: str = Field(..., min_length=1)
    mode: str = "full"


class AgentStepResponse(BaseModel):
    id: int
    run_id: int
    step_order: int
    node_name: str
    status: str
    input_json: Optional[dict] = None
    output_json: Optional[dict] = None
    error: Optional[str] = None
    duration_ms: Optional[float] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class FinanceAgentQueryResponse(BaseModel):
    answer: str
    citations: list[dict] = []
    facts: list[dict] = []
    calculations: list[dict] = []
    agent_run_id: int
    steps: list[dict] = []
    verification: dict = {}


class EvalDatasetResponse(BaseModel):
    id: int
    workspace_id: int
    name: str
    source: str
    version: str
    description: Optional[str] = None
    manifest_json: Optional[dict] = None
    case_count: int = 0
    frozen_at: Optional[datetime] = None
    source_url: Optional[str] = None
    license_note: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class EvalCaseResponse(BaseModel):
    id: int
    dataset_id: int
    case_uid: Optional[str] = None
    question: str
    expected_answer: Optional[str] = None
    expected_evidence: Optional[Any] = None
    expected_numeric: Optional[float] = None
    expected_calculation: Optional[Any] = None
    tolerance: float = 0.01
    task_type: Optional[str] = None
    difficulty: str = "medium"
    status: str = "draft"
    gold_filing_id: Optional[int] = None
    gold_document_id: Optional[int] = None
    rubric_json: Optional[Any] = None
    metadata_json: Optional[Any] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class EvalCaseUpdateRequest(BaseModel):
    status: Optional[str] = None
    expected_answer: Optional[str] = None
    expected_numeric: Optional[float] = None
    tolerance: Optional[float] = None
    difficulty: Optional[str] = None
    rubric_json: Optional[dict] = None


class FinanceEvaluationRunRequest(BaseModel):
    workspace_id: int = 1
    dataset_source: str = "custom_10k"
    strategy: str = "finance_agent"


class FinanceEvalJsonlImportRequest(BaseModel):
    dataset_name: str = "finance_agent_offline"
    file_path: str


class FinanceEvalJsonlExportResponse(BaseModel):
    dataset_id: int
    dataset_name: str
    file_path: str
    case_count: int


class FinanceEvaluationResultResponse(BaseModel):
    id: int
    workspace_id: int
    dataset_id: Optional[int] = None
    strategy: str
    metrics: Optional[dict] = None
    results: Optional[Any] = None
    created_at: datetime

    model_config = {"from_attributes": True}
