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
