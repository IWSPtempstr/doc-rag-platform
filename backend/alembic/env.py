from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool, create_engine

from alembic import context

# Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import all models so autogenerate can detect them
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.db import Base
from app.models import (
    DocumentModel, JobModel, ImageAssetModel,
    ChatSessionModel, ChatMessageModel,
    SettingsModel, CollectionModel, EvaluationRunModel,
    UserModel, WorkspaceModel, MembershipModel,
    CompanyModel, FilingModel, FilingSectionModel, FinancialFactModel,
    AgentRunModel, AgentStepModel, AgentArtifactModel,
    EvalDatasetModel, EvalCaseModel, EvalResultModel,
)
from app.config import config as app_config

target_metadata = Base.metadata


def get_url() -> str:
    url = app_config.DATABASE_URL
    if url.startswith("sqlite:///./"):
        url = url.replace("sqlite:///./", "sqlite:///")
    return url


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(get_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
