"""FastAPI 入口"""

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.db import engine, Base, ensure_sqlite_schema
from app.models import (
    DocumentModel, JobModel, ChatSessionModel, ChatMessageModel,
    SettingsModel, CollectionModel, EvaluationRunModel,
    # v3 finance models
    UserModel, WorkspaceModel, MembershipModel,
    CompanyModel, FilingModel, FilingSectionModel, FinancialFactModel,
    MarketFactModel,
    AgentRunModel, AgentStepModel, AgentArtifactModel,
    EvalDatasetModel, EvalCaseModel, EvalResultModel,
    ImageAssetModel,
)
from app.routers import documents, jobs, chat, settings, health, traces, evaluations, collections, auth, finance
from app.config import config

# 创建目录
for d in [
    config.STORAGE_DIR,
    config.DATA_DIR,
    config.PUBLIC_DATA_DIR,
    config.UPLOAD_DIR,
    config.CHROMA_DIR,
    config.TRACE_DIR,
    config.EVAL_DIR,
    config.ASSETS_DIR,
]:
    os.makedirs(d, exist_ok=True)

# 建表
Base.metadata.create_all(bind=engine)
ensure_sqlite_schema()

app = FastAPI(title="文档 RAG 平台", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_logger(request, call_next):
    import time
    t0 = time.time()
    response = await call_next(request)
    duration = (time.time() - t0) * 1000
    print(f"[rag-api] {request.method} {request.url.path} → {response.status_code} ({duration:.0f}ms)")
    return response


# 挂载路由
app.include_router(documents.router)
app.include_router(jobs.router)
app.include_router(chat.router)
app.include_router(settings.router)
app.include_router(health.router)
app.include_router(traces.router)
app.include_router(evaluations.router)
app.include_router(collections.router)
app.include_router(auth.router)
app.include_router(finance.router)

# v2.0: static file serving for extracted image assets
app.mount("/api/assets", StaticFiles(directory=config.ASSETS_DIR), name="assets")


@app.get("/")
def root():
    return {"app": "文档 RAG 平台", "version": "2.0.0"}
