"""SQLAlchemy 数据模型"""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Float, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.db import Base


def _utcnow():
    return datetime.now(timezone.utc)


class DocumentModel(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(500), nullable=False)
    stored_path = Column(String(1000), nullable=False)
    content_type = Column(String(50), nullable=False)
    size_bytes = Column(Integer, default=0)
    status = Column(String(20), default="pending")  # pending / processing / completed / failed
    tags = Column(String(500), default="")
    chunk_count = Column(Integer, default=0)
    image_count = Column(Integer, default=0)
    has_images = Column(Boolean, default=False)
    kb_version = Column(Integer, default=1)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    jobs = relationship("JobModel", back_populates="document", cascade="all, delete-orphan")
    images = relationship("ImageAssetModel", back_populates="document", cascade="all, delete-orphan")


class JobModel(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    type = Column(String(50), default="ingestion")
    status = Column(String(20), default="pending")  # pending / processing / completed / failed
    error = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    document = relationship("DocumentModel", back_populates="jobs")


class ImageAssetModel(Base):
    __tablename__ = "image_assets"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String(500), nullable=False)
    stored_path = Column(String(1000), nullable=False)
    source_page = Column(Integer, nullable=True)
    content_type = Column(String(50), nullable=False)
    size_bytes = Column(Integer, default=0)
    caption = Column(Text, nullable=True)
    caption_model = Column(String(200), nullable=True)
    caption_provider = Column(String(20), nullable=True)
    associated_chunks = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=_utcnow)

    document = relationship("DocumentModel", back_populates="images")


class UserModel(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    name = Column(String(200), nullable=False)
    password_hash = Column(String(500), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_utcnow)

    memberships = relationship("MembershipModel", back_populates="user", cascade="all, delete-orphan")


class WorkspaceModel(Base):
    __tablename__ = "workspaces"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    slug = Column(String(120), nullable=False, unique=True, index=True)
    created_at = Column(DateTime, default=_utcnow)

    memberships = relationship("MembershipModel", back_populates="workspace", cascade="all, delete-orphan")
    companies = relationship("CompanyModel", back_populates="workspace", cascade="all, delete-orphan")


class MembershipModel(Base):
    __tablename__ = "memberships"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(50), default="owner")
    created_at = Column(DateTime, default=_utcnow)

    user = relationship("UserModel", back_populates="memberships")
    workspace = relationship("WorkspaceModel", back_populates="memberships")


class CompanyModel(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    ticker = Column(String(20), nullable=False, index=True)
    name = Column(String(500), nullable=False)
    cik = Column(String(20), nullable=True, index=True)
    exchange = Column(String(50), nullable=True)
    industry = Column(String(200), nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    workspace = relationship("WorkspaceModel", back_populates="companies")
    filings = relationship("FilingModel", back_populates="company", cascade="all, delete-orphan")


class FilingModel(Base):
    __tablename__ = "filings"

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    accession_number = Column(String(80), nullable=True, index=True)
    filing_type = Column(String(20), default="10-K")
    fiscal_year = Column(Integer, nullable=False)
    filed_at = Column(DateTime, nullable=True)
    source_url = Column(String(1000), nullable=True)
    status = Column(String(30), default="imported")
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    company = relationship("CompanyModel", back_populates="filings")
    document = relationship("DocumentModel")
    sections = relationship("FilingSectionModel", back_populates="filing", cascade="all, delete-orphan")
    facts = relationship("FinancialFactModel", back_populates="filing", cascade="all, delete-orphan")


class FilingSectionModel(Base):
    __tablename__ = "filing_sections"

    id = Column(Integer, primary_key=True, index=True)
    filing_id = Column(Integer, ForeignKey("filings.id", ondelete="CASCADE"), nullable=False)
    item_code = Column(String(20), nullable=False)
    title = Column(String(300), nullable=False)
    content_preview = Column(Text, nullable=True)
    char_start = Column(Integer, default=0)
    char_end = Column(Integer, default=0)
    created_at = Column(DateTime, default=_utcnow)

    filing = relationship("FilingModel", back_populates="sections")


class FinancialFactModel(Base):
    __tablename__ = "financial_facts"

    id = Column(Integer, primary_key=True, index=True)
    filing_id = Column(Integer, ForeignKey("filings.id", ondelete="CASCADE"), nullable=False)
    metric = Column(String(120), nullable=False)
    label = Column(String(300), nullable=False)
    value = Column(Float, nullable=True)
    unit = Column(String(50), nullable=True)
    period = Column(String(50), nullable=True)
    source = Column(String(120), default="extracted")
    evidence = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True)
    created_at = Column(DateTime, default=_utcnow)

    filing = relationship("FilingModel", back_populates="facts")


class AgentRunModel(Base):
    __tablename__ = "agent_runs"

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="SET NULL"), nullable=True)
    filing_id = Column(Integer, ForeignKey("filings.id", ondelete="SET NULL"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    question = Column(Text, nullable=False)
    mode = Column(String(50), default="full")
    status = Column(String(30), default="running")
    answer = Column(Text, nullable=True)
    citations = Column(JSON, nullable=True)
    facts = Column(JSON, nullable=True)
    calculations = Column(JSON, nullable=True)
    verification = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    completed_at = Column(DateTime, nullable=True)

    steps = relationship("AgentStepModel", back_populates="run", cascade="all, delete-orphan")
    artifacts = relationship("AgentArtifactModel", back_populates="run", cascade="all, delete-orphan")


class AgentStepModel(Base):
    __tablename__ = "agent_steps"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False)
    step_order = Column(Integer, default=0)
    node_name = Column(String(120), nullable=False)
    status = Column(String(30), default="completed")
    input_json = Column(JSON, nullable=True)
    output_json = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    duration_ms = Column(Float, nullable=True)
    created_at = Column(DateTime, default=_utcnow)

    run = relationship("AgentRunModel", back_populates="steps")


class AgentArtifactModel(Base):
    __tablename__ = "agent_artifacts"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False)
    kind = Column(String(80), nullable=False)
    title = Column(String(300), nullable=False)
    payload = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=_utcnow)

    run = relationship("AgentRunModel", back_populates="artifacts")


class EvalDatasetModel(Base):
    __tablename__ = "eval_datasets"

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(200), nullable=False)
    source = Column(String(80), default="custom")
    version = Column(String(80), default="v1")
    description = Column(Text, nullable=True)
    manifest_json = Column(JSON, nullable=True)
    case_count = Column(Integer, default=0)
    frozen_at = Column(DateTime, nullable=True)
    source_url = Column(String(1000), nullable=True)
    license_note = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=_utcnow)

    cases = relationship("EvalCaseModel", back_populates="dataset", cascade="all, delete-orphan")


class EvalCaseModel(Base):
    __tablename__ = "eval_cases"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, ForeignKey("eval_datasets.id", ondelete="CASCADE"), nullable=False)
    case_uid = Column(String(200), nullable=True, index=True)
    question = Column(Text, nullable=False)
    expected_answer = Column(Text, nullable=True)
    expected_evidence = Column(JSON, nullable=True)
    expected_numeric = Column(Float, nullable=True)
    expected_calculation = Column(JSON, nullable=True)
    tolerance = Column(Float, default=0.01)
    task_type = Column(String(40), nullable=True)
    difficulty = Column(String(20), default="medium")
    status = Column(String(20), default="draft")
    gold_filing_id = Column(Integer, ForeignKey("filings.id", ondelete="SET NULL"), nullable=True)
    gold_document_id = Column(Integer, ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    rubric_json = Column(JSON, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=_utcnow)

    dataset = relationship("EvalDatasetModel", back_populates="cases")
    gold_filing = relationship("FilingModel")
    gold_document = relationship("DocumentModel")


class EvalResultModel(Base):
    __tablename__ = "eval_results"

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    dataset_id = Column(Integer, ForeignKey("eval_datasets.id", ondelete="SET NULL"), nullable=True)
    strategy = Column(String(80), default="finance_agent")
    metrics = Column(JSON, nullable=True)
    results = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=_utcnow)


class ChatSessionModel(Base):
    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), default="New Chat")
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    messages = relationship("ChatMessageModel", back_populates="session", cascade="all, delete-orphan")


class ChatMessageModel(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(20), nullable=False)  # user / assistant
    content = Column(Text, nullable=False)
    citations = Column(JSON, nullable=True)
    model = Column(String(200), nullable=True)
    cache_hit = Column(Boolean, default=False)
    created_at = Column(DateTime, default=_utcnow)

    session = relationship("ChatSessionModel", back_populates="messages")


class SettingsModel(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String(20), default="openai")  # legacy alias for chat_provider
    chat_provider = Column(String(20), default="openai")  # ollama / openai
    embedding_provider = Column(String(20), default="ollama")  # ollama / openai
    chat_model = Column(String(200), default="gpt-4o-mini")
    embed_model = Column(String(200), default="nomic-embed-text")
    top_k = Column(Integer, default=5)
    stream = Column(Boolean, default=True)
    vision_provider = Column(String(20), default="openai")
    vision_model = Column(String(200), default="deepseek-v4-pro")


class CollectionModel(Base):
    __tablename__ = "collections"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, unique=True)
    description = Column(Text, default="")
    document_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=_utcnow)


class EvaluationRunModel(Base):
    __tablename__ = "evaluation_runs"

    id = Column(Integer, primary_key=True, index=True)
    strategy = Column(String(50), nullable=False)  # dense / hybrid / hybrid_rerank
    hit_rate = Column(Float, nullable=True)
    context_precision = Column(Float, nullable=True)
    faithfulness = Column(Float, nullable=True)
    answer_relevancy = Column(Float, nullable=True)
    results = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
