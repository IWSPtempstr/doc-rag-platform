# 财报分析工作台 v2.0

SEC 10-K + Public Finance QA Workbench — 一个基于 FastAPI + Next.js + Redis + Chroma + LangGraph MAS 的财报分析工作台。项目主线只使用公开数据：SEC EDGAR 10-K / CompanyFacts、FinQA、TAT-QA；FinanceBench 仅作为非商用许可的补充评测集。

## 技术栈

| 组件 | 技术 |
|------|------|
| 后端 | FastAPI + SQLAlchemy + SQLite |
| 前端 | Next.js 14 + React 18 + TypeScript |
| 缓存/队列 | Redis (Streams, Cache, Rate Limit) |
| 向量库 | ChromaDB |
| PDF 处理 | PyMuPDF (fitz) |
| 视觉模型 | OpenAI-compatible Vision API (GPT-4o 等多模态模型) |
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

### v2.0
- 财报工作台：SEC EDGAR 10-K 导入、CompanyFacts/XBRL facts、10-K 章节浏览、Agent 分析轨迹
- 公共数据集闭环：SEC 10-K、Custom 10-K、FinQA、TAT-QA、FinanceBench sample 的导入、冻结、评估
- 数据治理：source/license/public_data_only/admissibility/failure_reason/coverage 元数据
- 中心化 LangGraph MAS：Retrieval、Fact Extraction、Calculation、Analysis、Verifier 节点记录 AgentStep
- Benchmark report：可输出公开数据集、覆盖率、失败原因和最新指标
- PDF 图片提取：PyMuPDF 提取 PDF 内嵌图片
- 图片上传：支持 PNG/JPG/GIF/WebP/BMP 作为独立文档
- Vision 描述生成：调用多模态 Vision API 为图片生成中文描述
- 图片资产管理：图片关联到 chunks，存储 source_page、caption、associated_chunks
- 文档重新索引：一键重置并重新处理文档，保留标签和元数据
- 文档详情页：展示 chunks + 图片资产 + 任务历史 + 进度追踪
- 增强文档列表：搜索、状态筛选、图片筛选、批量操作
- Docker 健康检查：所有服务（redis/backend/worker/frontend/mcp）添加 healthcheck
- 持久化卷文档：标注所有 Docker volume 的用途

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

## 公开数据 Demo 流程

```bash
cd workspace
set -a; source .env; set +a

# 后端、worker、前端启动后，在 /finance/evaluations 页面依次执行：
# 1. 导入 SEC 10-K 或绑定本地 10-K 文档
# 2. 构建 SEC 10-K 数据集
# 3. 生成自建 10-K Cases
# 4. 导入 FinQA Sample / TAT-QA Sample
# 5. 冻结数据集后运行评估

# 生成报告
PYTHONPATH=backend /root/anaconda3/envs/agent-learning/bin/python scripts/finance_benchmark_report.py --workspace-id 1
```

数据集冻结时会保留 approved 且 admissible 的 case。`custom_10k` 会记录 document/chunk/section/fact/chroma 覆盖，并将 `document_not_indexed`、`index_incomplete`、`gold_not_retrievable` 等失败原因留在 case metadata 中。

公开 benchmark 原始文件、FinQA/TAT-QA 派生文档、SEC EDGAR 导入的 10-K 文件统一放在 `/home/work/worktowork/data/public_datasets`。通过 `DATA_DIR` 和 `PUBLIC_DATA_DIR` 可以覆盖该路径。

### 本地开发

```bash
# 1. 安装 Python 依赖
pip install -r requirements.txt

# 2. 配置 Chat Provider 与 Embedding Provider
export CHAT_PROVIDER=openai
export CHAT_API_KEY=sk-...
export CHAT_API_BASE=https://your-api-endpoint.com
export CHAT_MODEL=your-chat-model
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
| DATA_DIR | /home/work/worktowork/data | 公开数据集与派生产物根目录 |
| PUBLIC_DATA_DIR | /home/work/worktowork/data/public_datasets | FinQA/TAT-QA/FinanceBench 等公开数据缓存 |
| CHAT_PROVIDER | openai | Chat Provider，支持 openai/ollama |
| CHAT_API_KEY | (空) | DeepSeek/OpenAI-compatible Chat API Key |
| CHAT_API_BASE | https://api.openai.com/v1 | Chat API Base |
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
| VISION_API_KEY | (CHAT_API_KEY) | Vision API Key，用于图片描述生成 |
| VISION_API_BASE | (CHAT_API_BASE) | Vision API Base |
| VISION_MODEL | gpt-4o | Vision 模型（需多模态模型） |
| AUTH_SECRET | change-me-in-production | HTTP-only JWT cookie 签名密钥 |
| SEC_USER_AGENT | FinancialRAGWorkbench/0.1 your-email@example.com | SEC EDGAR 请求必须配置的 User-Agent |
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

### v2.0

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/documents/{id}/reindex | 重新索引文档 |
| GET | /api/documents/{id}/assets | 文档图片资产 |
| GET | /api/documents/{id}/jobs | 文档任务历史 |
| GET | /api/assets/{path} | 图片静态文件（从 storage/assets 挂载） |

### 财报工作台

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/auth/login | 登录并写入 HTTP-only cookie |
| POST | /api/auth/logout | 退出登录 |
| GET | /api/auth/me | 当前用户与工作空间 |
| GET | /api/finance/summary | 财报工作台总览：公司、filings、数据集、失败原因 |
| GET | /api/finance/companies | 公司列表 |
| POST | /api/finance/companies | 新建公司 |
| POST | /api/finance/companies/{ticker}/filings/import | 从 SEC EDGAR 导入 10-K |
| GET | /api/finance/filings/{filing_id} | filing 详情 |
| GET | /api/finance/filings/{filing_id}/sections | 10-K 章节切分结果 |
| POST | /api/finance/filings/{filing_id}/bind-document | 绑定本地上传的财报文档 |
| POST | /api/finance/agent/query | 中心化 LangGraph MAS 分析 |
| POST | /api/finance/evaluations/run | 运行公开数据集评估 |
| GET | /api/finance/evaluations/results | 评估结果列表 |
| GET | /api/finance/datasets | 数据集列表 |
| POST | /api/finance/datasets/build/sec-10k | 构建 SEC 10-K 基准 |
| POST | /api/finance/datasets/build/custom-10k | 构建自建 10-K cases |
| POST | /api/finance/datasets/import/finqa | 导入 FinQA sample |
| POST | /api/finance/datasets/import/tatqa | 导入 TAT-QA sample |
| POST | /api/finance/datasets/import/financebench | 导入 FinanceBench sample |
| POST | /api/finance/datasets/{dataset_id}/freeze | 冻结数据集 |

### v1.1

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/collections | 集合列表 |
| GET | /api/documents/{id}/chunks | 文档 chunks |
| GET | /api/traces/ingestion | Ingestion trace |
| GET | /api/traces/query | Query trace |
| POST | /api/evaluations/run | 运行评估 |
| GET | /api/evaluations/results | 评估结果 |

## 评估产物

- `scripts/finance_benchmark_report.py`：从本地 SQLite 生成公开数据集报告（Markdown/JSON）
- `backend/tests/test_finance_public_datasets.py`：公开数据集导入与 manifest 约束测试

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

# v2.0 重新索引
curl -X POST http://localhost:8000/api/documents/1/reindex

# v2.0 查看图片资产
curl http://localhost:8000/api/documents/1/assets

# v2.0 查看文档任务历史
curl http://localhost:8000/api/documents/1/jobs

# v2.0 查看 chunks（含 image_refs）
curl http://localhost:8000/api/documents/1/chunks
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
│   │   │   ├── settings.py, health.py, auth.py
│   │   │   ├── traces.py, evaluations.py, collections.py
│   │   │   └── finance.py       # 财报工作台 API
│   │   └── services/            # 业务服务
│   │       ├── document_loader.py, splitter.py
│   │       ├── image_loader.py       # v2.0 PDF/图片提取
│   │       ├── vision_service.py     # v2.0 Vision 描述生成
│   │       ├── asset_service.py      # v2.0 图片资产管理
│   │       ├── embedding_provider.py, vector_store.py
│   │       ├── retriever.py, rag_service.py
│   │       ├── finance_agent.py, finance_dataset_builder.py, finance_evaluation.py
│   │       ├── sec_connector.py, finance_sections.py
│   │       ├── cache_service.py, rate_limit.py
│   │       ├── trace_service.py, evaluation_service.py
│   ├── Dockerfile
│   └── Dockerfile.worker
├── frontend/                    # Next.js 前端
│   ├── app/
│   │   ├── documents/           # 文档列表 + [id] 详情页
│   │   ├── finance/             # 财报工作台首页 / 公司 / Agent / 评估
│   │   ├── chat/                # 问答
│   │   ├── settings/            # 设置
│   │   ├── health/              # 健康检查
│   │   └── evaluations/         # 评估
│   └── lib/                      # API client + 类型定义
│       ├── api.ts
│       └── types.ts               # v2.0 TypeScript 类型定义
├── mcp/
│   └── server.py                # MCP server
├── scripts/
│   └── finance_benchmark_report.py
├── storage/                     # 数据存储
│   ├── uploads/, chroma/, traces/, evaluations/, assets/
├── docker-compose.yml
└── requirements.txt
```
