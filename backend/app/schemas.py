"""Pydantic Schema — API 输入输出"""

from datetime import datetime
from typing import Optional, Any
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
