"""应用配置，所有环境变量统一管理"""

import os


class Config:
    # Provider
    DEFAULT_CHAT_PROVIDER = os.getenv(
        "CHAT_PROVIDER",
        os.getenv("DEFAULT_CHAT_PROVIDER", os.getenv("DEFAULT_PROVIDER", "openai")),
    )
    DEFAULT_EMBEDDING_PROVIDER = os.getenv(
        "EMBEDDING_PROVIDER",
        os.getenv("DEFAULT_EMBEDDING_PROVIDER", "ollama"),
    )
    # Backward-compatible alias used by old code paths.
    DEFAULT_PROVIDER = DEFAULT_CHAT_PROVIDER

    # 数据库
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./storage/app.db")

    # Redis
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    RAG_CACHE_TTL_SECONDS = int(os.getenv("RAG_CACHE_TTL_SECONDS", "3600"))
    CHAT_RATE_LIMIT_PER_MINUTE = int(os.getenv("CHAT_RATE_LIMIT_PER_MINUTE", "20"))
    UPLOAD_RATE_LIMIT_PER_MINUTE = int(os.getenv("UPLOAD_RATE_LIMIT_PER_MINUTE", "10"))
    JOB_MAX_RETRIES = int(os.getenv("JOB_MAX_RETRIES", "3"))

    # 存储路径
    STORAGE_DIR = os.getenv("STORAGE_DIR", "storage")
    UPLOAD_DIR = os.path.join(STORAGE_DIR, "uploads")
    CHROMA_DIR = os.path.join(STORAGE_DIR, "chroma")
    TRACE_DIR = os.path.join(STORAGE_DIR, "traces")
    EVAL_DIR = os.path.join(STORAGE_DIR, "evaluations")

    # Ollama
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
    OLLAMA_CHAT_MODEL = os.getenv("OLLAMA_CHAT_MODEL", "qwen2.5:7b")

    # OpenAI-compatible API defaults. DeepSeek can be used for chat by setting CHAT_API_BASE.
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "")
    CHAT_API_KEY = os.getenv("CHAT_API_KEY") or OPENAI_API_KEY
    CHAT_API_BASE = os.getenv("CHAT_API_BASE") or OPENAI_API_BASE or "https://api.openai.com/v1"
    EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY") or OPENAI_API_KEY
    EMBEDDING_API_BASE = os.getenv("EMBEDDING_API_BASE") or OPENAI_API_BASE or "https://api.openai.com/v1"

    OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
    OPENAI_EMBED_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
    DEFAULT_CHAT_MODEL = os.getenv(
        "CHAT_MODEL",
        os.getenv("DEFAULT_CHAT_MODEL", OPENAI_CHAT_MODEL if DEFAULT_CHAT_PROVIDER == "openai" else OLLAMA_CHAT_MODEL),
    )
    DEFAULT_EMBED_MODEL = os.getenv(
        "EMBEDDING_MODEL",
        os.getenv(
            "DEFAULT_EMBED_MODEL",
            OLLAMA_EMBED_MODEL if DEFAULT_EMBEDDING_PROVIDER == "ollama" else OPENAI_EMBED_MODEL,
        ),
    )

    # RAG
    DEFAULT_TOP_K = int(os.getenv("DEFAULT_TOP_K", "5"))
    DEFAULT_CHUNK_SIZE = int(os.getenv("DEFAULT_CHUNK_SIZE", "500"))
    DEFAULT_CHUNK_OVERLAP = int(os.getenv("DEFAULT_CHUNK_OVERLAP", "50"))

    # v1.1
    RERANK_ENABLED = os.getenv("RERANK_ENABLED", "false").lower() == "true"

    # v2.0 — Vision (multimodal caption)
    VISION_API_KEY = os.getenv("VISION_API_KEY") or CHAT_API_KEY
    VISION_API_BASE = os.getenv("VISION_API_BASE") or CHAT_API_BASE
    VISION_MODEL = os.getenv("VISION_MODEL", "gpt-4o")
    ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
    ASSETS_DIR = os.path.join(STORAGE_DIR, "assets")

    # Auth / finance workspace defaults
    AUTH_SECRET = os.getenv("AUTH_SECRET", os.getenv("JWT_SECRET", "dev-only-change-me"))
    AUTH_COOKIE_NAME = os.getenv("AUTH_COOKIE_NAME", "rag_finance_session")
    AUTH_TOKEN_TTL_SECONDS = int(os.getenv("AUTH_TOKEN_TTL_SECONDS", "604800"))
    SEC_USER_AGENT = os.getenv("SEC_USER_AGENT", "FinancialRAGWorkbench/0.1 contact@example.com")


config = Config()
