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

        # Backfill legacy model names that no longer exist on the current provider.
        conn.execute(
            text(
                """
                UPDATE settings
                SET
                  provider = COALESCE(provider, :chat_provider),
                  chat_provider = COALESCE(chat_provider, provider, :chat_provider),
                  embedding_provider = COALESCE(embedding_provider, :embedding_provider),
                  vision_provider = COALESCE(vision_provider, :vision_provider)
                """
            ),
            {
                "chat_provider": config.DEFAULT_CHAT_PROVIDER,
                "embedding_provider": config.DEFAULT_EMBEDDING_PROVIDER,
                "vision_provider": "openai",
            },
        )
        conn.execute(
            text(
                """
                UPDATE settings
                SET
                  chat_model = CASE
                    WHEN COALESCE(chat_provider, provider) = :chat_provider
                         AND (chat_model IS NULL
                              OR chat_model = :legacy_chat_model_1
                              OR chat_model = :legacy_chat_model_2)
                    THEN :chat_model
                    ELSE chat_model
                  END,
                  embed_model = CASE
                    WHEN COALESCE(embedding_provider, :embedding_provider) = :embedding_provider
                         AND (embed_model IS NULL
                              OR embed_model = :legacy_embed_model_1
                              OR embed_model = :legacy_embed_model_2)
                    THEN :embed_model
                    ELSE embed_model
                  END,
                  vision_model = CASE
                    WHEN COALESCE(vision_provider, :vision_provider) = :vision_provider
                         AND (vision_model IS NULL
                              OR vision_model = :legacy_vision_model)
                    THEN :vision_model
                    ELSE vision_model
                  END
                """
            ),
            {
                "chat_provider": config.DEFAULT_CHAT_PROVIDER,
                "embedding_provider": config.DEFAULT_EMBEDDING_PROVIDER,
                "vision_provider": "openai",
                "chat_model": config.DEFAULT_CHAT_MODEL,
                "embed_model": config.DEFAULT_EMBED_MODEL,
                "vision_model": config.VISION_MODEL,
                "legacy_chat_model_1": "deepseek-v4-pro",
                "legacy_chat_model_2": "deepseek-v4-flash",
                "legacy_embed_model_1": "BAAI/bge-m3",
                "legacy_embed_model_2": "nomic-embed-text",
                "legacy_vision_model": "deepseek-v4-pro",
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

        # v3.0 — finance workbench tables
        _ensure_v3_tables(conn)


def _ensure_v3_tables(conn):
    """Create v3.0 tables for the finance workbench if they don't exist on existing DBs."""
    existing = {
        row[0]
        for row in conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table'")
        ).fetchall()
    }

    if "users" not in existing:
        conn.execute(text("""
            CREATE TABLE users (
                id INTEGER NOT NULL,
                email VARCHAR(255) NOT NULL,
                name VARCHAR(200) NOT NULL,
                password_hash VARCHAR(500) NOT NULL,
                is_active BOOLEAN DEFAULT 1,
                created_at DATETIME,
                PRIMARY KEY (id),
                UNIQUE (email)
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_users_id ON users (id)"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users (email)"))

    if "workspaces" not in existing:
        conn.execute(text("""
            CREATE TABLE workspaces (
                id INTEGER NOT NULL,
                name VARCHAR(200) NOT NULL,
                slug VARCHAR(120) NOT NULL,
                created_at DATETIME,
                PRIMARY KEY (id),
                UNIQUE (slug)
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_workspaces_id ON workspaces (id)"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_workspaces_slug ON workspaces (slug)"))

    if "memberships" not in existing:
        conn.execute(text("""
            CREATE TABLE memberships (
                id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                workspace_id INTEGER NOT NULL,
                role VARCHAR(50) DEFAULT 'owner',
                created_at DATETIME,
                PRIMARY KEY (id),
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
                FOREIGN KEY (workspace_id) REFERENCES workspaces (id) ON DELETE CASCADE
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_memberships_id ON memberships (id)"))

    if "companies" not in existing:
        conn.execute(text("""
            CREATE TABLE companies (
                id INTEGER NOT NULL,
                workspace_id INTEGER NOT NULL,
                ticker VARCHAR(20) NOT NULL,
                name VARCHAR(500) NOT NULL,
                cik VARCHAR(20),
                exchange VARCHAR(50),
                industry VARCHAR(200),
                created_at DATETIME,
                updated_at DATETIME,
                PRIMARY KEY (id),
                FOREIGN KEY (workspace_id) REFERENCES workspaces (id) ON DELETE CASCADE
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_companies_id ON companies (id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_companies_ticker ON companies (ticker)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_companies_cik ON companies (cik)"))

    if "filings" not in existing:
        conn.execute(text("""
            CREATE TABLE filings (
                id INTEGER NOT NULL,
                workspace_id INTEGER NOT NULL,
                company_id INTEGER NOT NULL,
                document_id INTEGER,
                accession_number VARCHAR(80),
                filing_type VARCHAR(20) DEFAULT 'annual_report',
                fiscal_year INTEGER NOT NULL,
                filed_at DATETIME,
                source_url VARCHAR(1000),
                status VARCHAR(30) DEFAULT 'imported',
                metadata_json JSON,
                created_at DATETIME,
                updated_at DATETIME,
                PRIMARY KEY (id),
                FOREIGN KEY (workspace_id) REFERENCES workspaces (id) ON DELETE CASCADE,
                FOREIGN KEY (company_id) REFERENCES companies (id) ON DELETE CASCADE,
                FOREIGN KEY (document_id) REFERENCES documents (id) ON DELETE SET NULL
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_filings_id ON filings (id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_filings_accession ON filings (accession_number)"))

    if "filing_sections" not in existing:
        conn.execute(text("""
            CREATE TABLE filing_sections (
                id INTEGER NOT NULL,
                filing_id INTEGER NOT NULL,
                item_code VARCHAR(20) NOT NULL,
                title VARCHAR(300) NOT NULL,
                content_preview TEXT,
                char_start INTEGER DEFAULT 0,
                char_end INTEGER DEFAULT 0,
                created_at DATETIME,
                PRIMARY KEY (id),
                FOREIGN KEY (filing_id) REFERENCES filings (id) ON DELETE CASCADE
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_filing_sections_id ON filing_sections (id)"))

    if "financial_facts" not in existing:
        conn.execute(text("""
            CREATE TABLE financial_facts (
                id INTEGER NOT NULL,
                filing_id INTEGER NOT NULL,
                metric VARCHAR(120) NOT NULL,
                label VARCHAR(300) NOT NULL,
                value FLOAT,
                unit VARCHAR(50),
                period VARCHAR(50),
                source VARCHAR(120) DEFAULT 'extracted',
                evidence TEXT,
                confidence FLOAT,
                created_at DATETIME,
                PRIMARY KEY (id),
                FOREIGN KEY (filing_id) REFERENCES filings (id) ON DELETE CASCADE
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_financial_facts_id ON financial_facts (id)"))

    if "market_facts" not in existing:
        conn.execute(text("""
            CREATE TABLE market_facts (
                id INTEGER NOT NULL,
                workspace_id INTEGER NOT NULL,
                company_id INTEGER NOT NULL,
                ticker VARCHAR(20) NOT NULL,
                trade_date VARCHAR(20) NOT NULL,
                metric VARCHAR(120) NOT NULL,
                label VARCHAR(300) NOT NULL,
                value FLOAT,
                unit VARCHAR(50),
                source VARCHAR(120) DEFAULT 'akshare',
                source_url VARCHAR(1000),
                confidence FLOAT,
                metadata_json JSON,
                created_at DATETIME,
                PRIMARY KEY (id),
                FOREIGN KEY (workspace_id) REFERENCES workspaces (id) ON DELETE CASCADE,
                FOREIGN KEY (company_id) REFERENCES companies (id) ON DELETE CASCADE
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_market_facts_id ON market_facts (id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_market_facts_ticker ON market_facts (ticker)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_market_facts_trade_date ON market_facts (trade_date)"))

    if "user_watchlists" not in existing:
        conn.execute(text("""
            CREATE TABLE user_watchlists (
                id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                workspace_id INTEGER NOT NULL,
                ticker VARCHAR(20) NOT NULL,
                priority INTEGER DEFAULT 100,
                created_at DATETIME,
                PRIMARY KEY (id),
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
                FOREIGN KEY (workspace_id) REFERENCES workspaces (id) ON DELETE CASCADE
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_user_watchlists_id ON user_watchlists (id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_user_watchlists_ticker ON user_watchlists (ticker)"))

    if "sentiment_facts" not in existing:
        conn.execute(text("""
            CREATE TABLE sentiment_facts (
                id INTEGER NOT NULL,
                workspace_id INTEGER NOT NULL,
                ticker VARCHAR(20),
                trade_date VARCHAR(20) NOT NULL,
                scope VARCHAR(50) DEFAULT 'market',
                score FLOAT,
                label VARCHAR(120),
                source VARCHAR(120) DEFAULT 'akshare',
                evidence TEXT,
                metadata_json JSON,
                created_at DATETIME,
                PRIMARY KEY (id),
                FOREIGN KEY (workspace_id) REFERENCES workspaces (id) ON DELETE CASCADE
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_sentiment_facts_id ON sentiment_facts (id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_sentiment_facts_ticker ON sentiment_facts (ticker)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_sentiment_facts_trade_date ON sentiment_facts (trade_date)"))

    if "daily_briefs" not in existing:
        conn.execute(text("""
            CREATE TABLE daily_briefs (
                id INTEGER NOT NULL,
                workspace_id INTEGER NOT NULL,
                user_id INTEGER,
                trade_date VARCHAR(20) NOT NULL,
                status VARCHAR(30) DEFAULT 'generated',
                summary TEXT,
                items JSON,
                metadata_json JSON,
                generated_at DATETIME,
                PRIMARY KEY (id),
                FOREIGN KEY (workspace_id) REFERENCES workspaces (id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_daily_briefs_id ON daily_briefs (id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_daily_briefs_trade_date ON daily_briefs (trade_date)"))

    if "data_sync_jobs" not in existing:
        conn.execute(text("""
            CREATE TABLE data_sync_jobs (
                id INTEGER NOT NULL,
                workspace_id INTEGER NOT NULL,
                job_type VARCHAR(80) NOT NULL,
                source VARCHAR(120) NOT NULL,
                status VARCHAR(30) DEFAULT 'running',
                started_at DATETIME,
                completed_at DATETIME,
                failure_reason TEXT,
                metrics JSON,
                PRIMARY KEY (id),
                FOREIGN KEY (workspace_id) REFERENCES workspaces (id) ON DELETE CASCADE
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_data_sync_jobs_id ON data_sync_jobs (id)"))

    if "agent_runs" not in existing:
        conn.execute(text("""
            CREATE TABLE agent_runs (
                id INTEGER NOT NULL,
                workspace_id INTEGER NOT NULL,
                company_id INTEGER,
                filing_id INTEGER,
                user_id INTEGER,
                question TEXT NOT NULL,
                mode VARCHAR(50) DEFAULT 'full',
                status VARCHAR(30) DEFAULT 'running',
                answer TEXT,
                citations JSON,
                facts JSON,
                calculations JSON,
                verification JSON,
                created_at DATETIME,
                completed_at DATETIME,
                PRIMARY KEY (id),
                FOREIGN KEY (workspace_id) REFERENCES workspaces (id) ON DELETE CASCADE,
                FOREIGN KEY (company_id) REFERENCES companies (id) ON DELETE SET NULL,
                FOREIGN KEY (filing_id) REFERENCES filings (id) ON DELETE SET NULL,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE SET NULL
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_runs_id ON agent_runs (id)"))

    if "agent_steps" not in existing:
        conn.execute(text("""
            CREATE TABLE agent_steps (
                id INTEGER NOT NULL,
                run_id INTEGER NOT NULL,
                step_order INTEGER DEFAULT 0,
                node_name VARCHAR(120) NOT NULL,
                status VARCHAR(30) DEFAULT 'completed',
                input_json JSON,
                output_json JSON,
                error TEXT,
                duration_ms FLOAT,
                created_at DATETIME,
                PRIMARY KEY (id),
                FOREIGN KEY (run_id) REFERENCES agent_runs (id) ON DELETE CASCADE
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_steps_id ON agent_steps (id)"))

    if "agent_artifacts" not in existing:
        conn.execute(text("""
            CREATE TABLE agent_artifacts (
                id INTEGER NOT NULL,
                run_id INTEGER NOT NULL,
                kind VARCHAR(80) NOT NULL,
                title VARCHAR(300) NOT NULL,
                payload JSON,
                created_at DATETIME,
                PRIMARY KEY (id),
                FOREIGN KEY (run_id) REFERENCES agent_runs (id) ON DELETE CASCADE
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_artifacts_id ON agent_artifacts (id)"))

    if "eval_datasets" not in existing:
        conn.execute(text("""
            CREATE TABLE eval_datasets (
                id INTEGER NOT NULL,
                workspace_id INTEGER NOT NULL,
                name VARCHAR(200) NOT NULL,
                source VARCHAR(80) DEFAULT 'custom',
                version VARCHAR(80) DEFAULT 'v1',
                description TEXT,
                created_at DATETIME,
                PRIMARY KEY (id),
                FOREIGN KEY (workspace_id) REFERENCES workspaces (id) ON DELETE CASCADE
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_eval_datasets_id ON eval_datasets (id)"))

    if "eval_cases" not in existing:
        conn.execute(text("""
            CREATE TABLE eval_cases (
                id INTEGER NOT NULL,
                dataset_id INTEGER NOT NULL,
                question TEXT NOT NULL,
                expected_answer TEXT,
                expected_evidence JSON,
                expected_numeric FLOAT,
                tolerance FLOAT DEFAULT 0.01,
                metadata_json JSON,
                created_at DATETIME,
                PRIMARY KEY (id),
                FOREIGN KEY (dataset_id) REFERENCES eval_datasets (id) ON DELETE CASCADE
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_eval_cases_id ON eval_cases (id)"))

    # v3.1 — new columns on eval_datasets and eval_cases
    ds_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(eval_datasets)")).fetchall()} if "eval_datasets" in existing else set()
    if "manifest_json" not in ds_cols:
        conn.execute(text("ALTER TABLE eval_datasets ADD COLUMN manifest_json JSON"))
    if "case_count" not in ds_cols:
        conn.execute(text("ALTER TABLE eval_datasets ADD COLUMN case_count INTEGER DEFAULT 0"))
    if "frozen_at" not in ds_cols:
        conn.execute(text("ALTER TABLE eval_datasets ADD COLUMN frozen_at DATETIME"))
    if "source_url" not in ds_cols:
        conn.execute(text("ALTER TABLE eval_datasets ADD COLUMN source_url VARCHAR(1000)"))
    if "license_note" not in ds_cols:
        conn.execute(text("ALTER TABLE eval_datasets ADD COLUMN license_note VARCHAR(500)"))

    case_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(eval_cases)")).fetchall()} if "eval_cases" in existing else set()
    if "case_uid" not in case_cols:
        conn.execute(text("ALTER TABLE eval_cases ADD COLUMN case_uid VARCHAR(200)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_eval_cases_case_uid ON eval_cases (case_uid)"))
    if "task_type" not in case_cols:
        conn.execute(text("ALTER TABLE eval_cases ADD COLUMN task_type VARCHAR(40)"))
    if "difficulty" not in case_cols:
        conn.execute(text("ALTER TABLE eval_cases ADD COLUMN difficulty VARCHAR(20) DEFAULT 'medium'"))
    if "status" not in case_cols:
        conn.execute(text("ALTER TABLE eval_cases ADD COLUMN status VARCHAR(20) DEFAULT 'draft'"))
    if "gold_filing_id" not in case_cols:
        conn.execute(text("ALTER TABLE eval_cases ADD COLUMN gold_filing_id INTEGER REFERENCES filings (id) ON DELETE SET NULL"))
    if "gold_document_id" not in case_cols:
        conn.execute(text("ALTER TABLE eval_cases ADD COLUMN gold_document_id INTEGER REFERENCES documents (id) ON DELETE SET NULL"))
    if "expected_calculation" not in case_cols:
        conn.execute(text("ALTER TABLE eval_cases ADD COLUMN expected_calculation JSON"))
    if "rubric_json" not in case_cols:
        conn.execute(text("ALTER TABLE eval_cases ADD COLUMN rubric_json JSON"))

    if "eval_results" not in existing:
        conn.execute(text("""
            CREATE TABLE eval_results (
                id INTEGER NOT NULL,
                workspace_id INTEGER NOT NULL,
                dataset_id INTEGER,
                strategy VARCHAR(80) DEFAULT 'finance_agent',
                metrics JSON,
                results JSON,
                created_at DATETIME,
                PRIMARY KEY (id),
                FOREIGN KEY (workspace_id) REFERENCES workspaces (id) ON DELETE CASCADE,
                FOREIGN KEY (dataset_id) REFERENCES eval_datasets (id) ON DELETE SET NULL
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_eval_results_id ON eval_results (id)"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
