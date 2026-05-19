# 文档 RAG 平台 v1.1

Document Retrieval-Augmented Generation Platform — 一个基于 FastAPI + Next.js + Redis + Chroma + DeepSeek/OpenAI-compatible API + Ollama Embedding 的文档问答平台。

## 技术栈

| 组件 | 技术 |
|------|------|
| 后端 | FastAPI + SQLAlchemy + SQLite |
| 前端 | Next.js 14 + React 18 + TypeScript |
| 缓存/队列 | Redis (Streams, Cache, Rate Limit) |
| 向量库 | ChromaDB |
| LLM/Embedding | Chat 使用 DeepSeek/OpenAI-compatible API，Embedding 默认使用本地 Ollama |
| MCP | Python stdin/stdout JSON-RPC |

## 功能

### v1
- 文档上传（PDF/DOCX/MD/TXT）和 CRUD 管理
- 异步任务处理（Redis Streams + Worker）
- 实时进度追踪
- RAG 问答（Dense Retrieval + LLM Generation）
- Redis 缓存（cache-aside pattern）
- 接口限流
- Chat Session/Message 历史
- Chat Provider 与 Embedding Provider 独立配置
- 健康检查（SQLite/Redis/Chroma/Provider/Queue）

### v1.1
- Hybrid Search: Dense + BM25 Sparse + RRF Fusion
- 可选 Rerank
- Trace: Ingestion Trace / Query Trace (JSONL)
- Evaluation: Golden Questions (Hit Rate, Context Precision, Faithfulness, Answer Relevancy)
- Collections 管理
- 扩展 MCP 工具

## 快速启动

### 前置条件

- Docker 和 Docker Compose
- Chat API Key：DeepSeek 或兼容 `/v1/chat/completions` 的服务
- 本地 Embedding：Ollama + `nomic-embed-text`
- 或：Python 3.12+, Node.js 20+, Redis 7+, Ollama

### Docker Compose 启动

```bash
cd workspace
cp .env.example .env
# 编辑 .env，填入 CHAT_API_KEY，默认 Chat 走 DeepSeek，Embedding 走本地 Ollama
docker compose up
```

访问：
- 前端：http://localhost:3000
- 后端 API：http://localhost:8000
- API 文档：http://localhost:8000/docs

### 本地开发

```bash
# 1. 安装 Python 依赖
pip install -r requirements.txt

# 2. 配置 Chat Provider 与 Embedding Provider
export CHAT_PROVIDER=openai
export CHAT_API_KEY=sk-...
export CHAT_API_BASE=https://api.deepseek.com
export CHAT_MODEL=deepseek-v4-flash
export EMBEDDING_PROVIDER=ollama
export EMBEDDING_MODEL=nomic-embed-text
export OLLAMA_BASE_URL=http://localhost:11434

# 3. 启动 Redis
redis-server

# 4. 启动后端
cd backend
uvicorn app.main:app --reload --port 8000

# 5. 启动 Worker
python -m app.worker

# 6. 启动前端
cd frontend
npm install
npm run dev

# 7. 启动 MCP Server
cd mcp
python server.py
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| DATABASE_URL | sqlite:///./storage/app.db | SQLite 路径 |
| REDIS_URL | redis://localhost:6379/0 | Redis 连接 |
| CHAT_PROVIDER | openai | Chat Provider，支持 openai/ollama |
| CHAT_API_KEY | (空) | DeepSeek/OpenAI-compatible Chat API Key |
| CHAT_API_BASE | https://api.deepseek.com | Chat API Base |
| CHAT_MODEL | deepseek-v4-flash | Chat 模型 |
| EMBEDDING_PROVIDER | ollama | Embedding Provider，支持 ollama/openai |
| EMBEDDING_MODEL | nomic-embed-text | Embedding 模型 |
| EMBEDDING_API_KEY | (空) | API embedding key，仅 `EMBEDDING_PROVIDER=openai` 时需要 |
| EMBEDDING_API_BASE | https://api.openai.com/v1 | API embedding base |
| OPENAI_API_KEY | (空) | 兼容旧变量，作为 `CHAT_API_KEY` 回退 |
| OPENAI_API_BASE | (空) | 兼容旧变量，作为 `CHAT_API_BASE` 回退 |
| OLLAMA_BASE_URL | http://localhost:11434 | Ollama API |
| RAG_CACHE_TTL_SECONDS | 3600 | 缓存过期(秒) |
| CHAT_RATE_LIMIT_PER_MINUTE | 20 | 问答限流 |
| UPLOAD_RATE_LIMIT_PER_MINUTE | 10 | 上传限流 |
| JOB_MAX_RETRIES | 3 | 任务最大重试 |
| DEFAULT_TOP_K | 5 | 检索结果数 |
| DEFAULT_CHUNK_SIZE | 500 | 切片大小 |
| DEFAULT_CHUNK_OVERLAP | 50 | 切片重叠 |
| RERANK_ENABLED | false | 启用 Rerank |

## 本地 Embedding 可行性

当前默认由本地 Ollama 的 `nomic-embed-text` 负责向量化，Chat 由 DeepSeek/OpenAI-compatible API 负责生成回答。这个组合用于避开本地 7B Chat 推理的 GPU/内存不稳定问题，同时保留本地向量化能力。

已验证的本地条件：

- `nomic-embed-text` 已安装，模型约 274 MB。
- 本地 embedding 调用可返回 768 维向量。
- RTX 4060 Ti 可被 WSL 识别，但 Ollama Chat 7B 曾出现 CPU 路径和 runner 退出问题。
- 文档向量按 embedding 配置写入独立 Chroma collection，例如 `documents__ollama__nomic-embed-text`。

切换 `EMBEDDING_PROVIDER` 或 `EMBEDDING_MODEL` 后，需要重新索引文档。不同 embedding 模型的向量维度可能不同，不能混用同一个 Chroma collection。

## API 概览

### v1

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/documents/upload | 上传文档 |
| GET | /api/documents | 文档列表 |
| GET | /api/documents/{id} | 文档详情 |
| PATCH | /api/documents/{id} | 更新文档 |
| DELETE | /api/documents/{id} | 删除文档 |
| GET | /api/jobs/{job_id} | 任务状态 |
| POST | /api/chat/query | RAG 问答 |
| GET | /api/chat/sessions | 会话列表 |
| POST | /api/settings/provider | 更新设置 |
| GET | /api/health | 健康检查 |

### v1.1

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/collections | 集合列表 |
| GET | /api/documents/{id}/chunks | 文档 chunks |
| GET | /api/traces/ingestion | Ingestion trace |
| GET | /api/traces/query | Query trace |
| POST | /api/evaluations/run | 运行评估 |
| GET | /api/evaluations/results | 评估结果 |

## MCP 工具

| 工具 | 说明 |
|------|------|
| search_documents | 搜索文档向量库 |
| ask_knowledge_base | 向知识库提问 |
| query_knowledge_hub | 通用知识库查询 |
| list_collections | 列出所有集合 |
| get_document_summary | 获取文档摘要 |

## cURL 示例

```bash
# 上传文档
curl -F "file=@test.pdf" -F "tags=技术文档" http://localhost:8000/api/documents/upload

# 问答
curl -X POST http://localhost:8000/api/chat/query \
  -H "Content-Type: application/json" \
  -d '{"question": "什么是RAG？"}'

# 健康检查
curl http://localhost:8000/api/health

# 运行评估
curl -X POST http://localhost:8000/api/evaluations/run \
  -H "Content-Type: application/json" \
  -d '{"strategy": "hybrid"}'
```

## 目录结构

```
workspace/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 入口
│   │   ├── config.py            # 配置
│   │   ├── db.py                # 数据库
│   │   ├── models.py            # SQLAlchemy 模型
│   │   ├── schemas.py           # Pydantic Schema
│   │   ├── redis_client.py      # Redis 客户端
│   │   ├── worker.py            # 异步 Worker
│   │   ├── routers/             # API 路由
│   │   │   ├── documents.py, jobs.py, chat.py
│   │   │   ├── settings.py, health.py
│   │   │   ├── traces.py, evaluations.py, collections.py
│   │   └── services/            # 业务服务
│   │       ├── document_loader.py, splitter.py
│   │       ├── embedding_provider.py, vector_store.py
│   │       ├── retriever.py, rag_service.py
│   │       ├── cache_service.py, rate_limit.py
│   │       ├── trace_service.py, evaluation_service.py
│   ├── Dockerfile
│   └── Dockerfile.worker
├── frontend/                    # Next.js 前端
│   ├── app/
│   │   ├── documents/           # 文档管理
│   │   ├── chat/                # 问答
│   │   ├── settings/            # 设置
│   │   ├── health/              # 健康检查
│   │   └── evaluations/         # 评估
│   └── lib/api.ts               # API client
├── mcp/
│   └── server.py                # MCP server
├── storage/                     # 数据存储
│   ├── uploads/, chroma/, traces/, evaluations/
├── docker-compose.yml
└── requirements.txt
```
