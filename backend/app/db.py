"""数据库引擎和会话管理"""

import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import config

os.makedirs(config.STORAGE_DIR, exist_ok=True)

engine = create_engine(
    config.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in config.DATABASE_URL else {},
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def ensure_sqlite_schema():
    """Add small SQLite columns that create_all cannot backfill on existing DBs."""
    if not config.DATABASE_URL.startswith("sqlite"):
        return

    with engine.begin() as conn:
        tables = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='settings'")).fetchall()
        if not tables:
            return

        rows = conn.execute(text("PRAGMA table_info(settings)")).fetchall()
        columns = {row[1] for row in rows}

        if "chat_provider" not in columns:
            conn.execute(text("ALTER TABLE settings ADD COLUMN chat_provider VARCHAR(20)"))
        if "embedding_provider" not in columns:
            conn.execute(text("ALTER TABLE settings ADD COLUMN embedding_provider VARCHAR(20)"))
        if "vision_provider" not in columns:
            conn.execute(text("ALTER TABLE settings ADD COLUMN vision_provider VARCHAR(20)"))
        if "vision_model" not in columns:
            conn.execute(text("ALTER TABLE settings ADD COLUMN vision_model VARCHAR(200)"))

        # v1.1 default fill
        conn.execute(
            text(
                """
                UPDATE settings
                SET
                  chat_provider = COALESCE(chat_provider, provider, :chat_provider),
                  embedding_provider = COALESCE(embedding_provider, :embedding_provider),
                  chat_model = COALESCE(chat_model, :chat_model),
                  embed_model = COALESCE(embed_model, :embed_model)
                """
            ),
            {
                "chat_provider": config.DEFAULT_CHAT_PROVIDER,
                "embedding_provider": config.DEFAULT_EMBEDDING_PROVIDER,
                "chat_model": config.DEFAULT_CHAT_MODEL,
                "embed_model": config.DEFAULT_EMBED_MODEL,
            },
        )

        # v2.0 — documents new columns
        doc_cols = conn.execute(text("PRAGMA table_info(documents)")).fetchall()
        doc_columns = {row[1] for row in doc_cols}
        if "image_count" not in doc_columns:
            conn.execute(text("ALTER TABLE documents ADD COLUMN image_count INTEGER DEFAULT 0"))
        if "has_images" not in doc_columns:
            conn.execute(text("ALTER TABLE documents ADD COLUMN has_images BOOLEAN DEFAULT 0"))

        # v2.0 — create image_assets table if missing
        img_tables = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='image_assets'")).fetchall()
        if not img_tables:
            conn.execute(text("""
                CREATE TABLE image_assets (
                    id INTEGER NOT NULL,
                    document_id INTEGER NOT NULL,
                    filename VARCHAR(500) NOT NULL,
                    stored_path VARCHAR(1000) NOT NULL,
                    source_page INTEGER,
                    content_type VARCHAR(50) NOT NULL,
                    size_bytes INTEGER DEFAULT 0,
                    caption TEXT,
                    caption_model VARCHAR(200),
                    caption_provider VARCHAR(20),
                    associated_chunks JSON,
                    created_at DATETIME,
                    PRIMARY KEY (id),
                    FOREIGN KEY (document_id) REFERENCES documents (id) ON DELETE CASCADE
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_image_assets_id ON image_assets (id)"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
