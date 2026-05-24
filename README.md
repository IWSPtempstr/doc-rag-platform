# A 股公告与情绪分析工作台

面向 A 股上市公司的公告、财报、行情热度与市场情绪研究辅助系统。项目主线已经收敛为 A 股公开数据，不再把 SEC、FinQA、TAT-QA、FinanceBench 或通用文档 RAG 作为产品入口。

系统提供两类视角：

- 普通用户：每日简报、关注公司、热点 Top20、公告资产、公司详情、个性化分析和历史查询。
- 管理员：数据源连接、日更任务、同步日志、评估管理、健康检查和索引诊断。

分析结果定位为研究辅助：解释“为什么今天值得关注”，展示公告、财务事实、行情热度和市场情绪的可用依据；不输出买卖建议、目标价或交易信号。

## 当前能力

### 用户侧

- `/finance`：用户首页，展示每日简报、关注公司、热点 Top20、市场情绪趋势、异常公告入口和个性化分析入口。
- `/finance/companies/{ticker}`：公司详情页，优先展示业务摘要、今日变化、可用信号、缺失信息和下一步补全动作。
- `/finance/agent`：A 股个性化分析页，支持历史查询记录展示和删除。
- `/documents`：公告资产页，用于查看已导入公告/年报和索引状态。

普通用户不会看到数据源管理、评估管理、系统设置、健康检查和底层索引诊断入口。

### 管理员侧

- `/finance/connectors`：CNINFO、AKShare、TuShare、A 股 MCP、Chroma 等连接状态和失败原因。
- `/finance/evaluations`：A 股专项评估结果与失败原因分布。
- 后端 `/api/admin/finance/*`：连接器测试、日更任务、同步历史和评估结果。
- 技术诊断：公司数据覆盖、文档索引、section、chunk、fact、Chroma 覆盖情况。

### 数据链路

- CNINFO 公告/年报导入后生成 `Document / Filing`，并进入 worker 索引流程。
- AKShare/TuShare 同步结构化财务事实，写入 `FinancialFact`。
- 行情热度写入 `MarketFact`，市场级情绪写入 `SentimentFact`。
- 每日简报 Top20、用户关注、公告搜索会自动生成 RAG context 文档，并进入 Chroma 索引，保证后续 Agent 能检索到这些上下文。
- 公司数据不足时，后端 `research_summary` 会统一返回可用信号、缺失项、缺失原因、可执行动作和分析边界，避免页面空白或编造基本面结论。

### 每日简报规则

- 用户没有关注公司时：展示当日市场热度 Top20。
- 用户已有关注公司时：先展示关注公司，再展示去重后的市场热度 Top20。
- 热榜来源优先使用 AKShare 东方财富热榜；失败时降级到行情、涨跌幅、成交额、公告数量等可用信号。
- 市场情绪优先使用 AKShare 新闻情绪接口；接口失败时写入本地覆盖型 fallback 记录，并展示同步状态和失败原因。

## 技术栈

| 层 | 技术 |
| --- | --- |
| 后端 | FastAPI + SQLAlchemy + SQLite |
| 前端 | Next.js 14 + React 18 + TypeScript |
| 队列/缓存 | Redis |
| 向量索引 | ChromaDB |
| 文档处理 | PyMuPDF、文档切片、图片 caption |
| Agent | LangGraph MAS + deterministic calculation + verifier |
| 数据源 | CNINFO、AKShare、TuShare、A 股 MCP provider |
| 评估与追踪 | EvalDataset/EvalCase/EvalResult、AgentRun/AgentStep、JSONL trace |

## 快速启动

### Docker Compose

```bash
cd /home/work/worktowork/workspace
cp .env.example .env
docker compose up -d --build
```

访问地址：

- 前端：http://localhost:3000
- 后端 API：http://localhost:8000
- API 文档：http://localhost:8000/docs

如果只修改前端或后端代码，可按服务重建：

```bash
docker compose up -d --build backend worker frontend
```

### 本地 conda 开发

本地 Python 环境使用 `agent-learning`，配置读取 `/home/work/worktowork/workspace/.env`。

```bash
cd /home/work/worktowork/workspace
set -a; source .env; set +a

# 后端
PYTHONPATH=backend /root/anaconda3/envs/agent-learning/bin/python -m uvicorn app.main:app --app-dir backend --reload --port 8000

# worker
PYTHONPATH=backend /root/anaconda3/envs/agent-learning/bin/python -m app.worker

# 前端
cd frontend
npm install
npm run dev
```

## Demo 账号

Docker 演示库中可使用：

| 角色 | 邮箱 | 密码 |
| --- | --- | --- |
| 普通用户 | `user@example.com` | `user123456` |
| 管理员 | `manager@example.com` | `admin123456` |

登录后普通用户默认进入 `/finance`；管理员可进入 `/finance/connectors` 等管理页面。

## Demo 流程

1. 使用普通用户登录，进入 `/finance`。
2. 查看每日简报。没有关注公司时，系统展示市场热度 Top20；点击条目进入公司详情。
3. 添加关注公司，例如 `600519`。关注动作会写入用户 watchlist，并生成可检索的 RAG context。
4. 在公司详情页查看研究摘要：当前能判断什么、不能判断什么、缺失原因和下一步补全动作。
5. 进入 `/finance/agent` 提问，例如“结合公告、财务事实、行情热度和市场情绪，解释这家公司今天需要关注的变化。”
6. 查看历史查询记录；不需要的记录可删除。
7. 使用管理员登录，进入 `/finance/connectors`，运行连接器测试或手动触发日更任务。

## 主要 API

### Auth

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/auth/login` | 登录并写入 HTTP-only cookie |
| POST | `/api/auth/logout` | 退出登录 |
| GET | `/api/auth/me` | 当前用户、工作空间与角色 |

### 用户侧 Finance API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/finance/watchlist` | 关注公司列表 |
| POST | `/api/finance/watchlist` | 添加或更新关注公司，并写入 RAG context |
| DELETE | `/api/finance/watchlist/{ticker}` | 取消关注公司 |
| GET | `/api/finance/daily-brief` | 获取站内每日简报 |
| GET | `/api/finance/companies` | A 股公司列表 |
| POST | `/api/finance/companies` | 创建轻量公司记录 |
| GET | `/api/finance/companies/{ticker}` | 公司详情 |
| GET | `/api/finance/companies/{ticker}/research-summary` | 公司研究摘要与数据缺失说明 |
| GET | `/api/finance/ashare/companies/{ticker}/announcements` | 检索 CNINFO 公告，并写入 RAG context |
| POST | `/api/finance/ashare/companies/{ticker}/filings/import` | 导入年报公告 |
| POST | `/api/finance/ashare/companies/{ticker}/facts/sync` | 同步结构化财务事实 |
| POST | `/api/finance/ashare/companies/{ticker}/market/sync` | 同步行情事实 |
| GET | `/api/finance/sentiment` | 查询市场或个股情绪事实 |
| POST | `/api/finance/agent/query` | 运行个性化分析 Agent |
| GET | `/api/finance/agent/runs` | 查询个人历史分析记录 |
| DELETE | `/api/finance/agent/runs/{run_id}` | 删除个人历史分析记录 |
| GET | `/api/finance/agent/runs/{run_id}/trace` | 查询单次 Agent 轨迹 |

### 管理员 API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/admin/finance/connectors/status` | 数据源与索引状态 |
| POST | `/api/admin/finance/connectors/{name}/test` | 连接器测试 |
| POST | `/api/admin/finance/jobs/daily-sync/run` | 手动运行日更任务 |
| GET | `/api/admin/finance/jobs/daily-sync/history` | 日更历史 |
| GET | `/api/admin/finance/evaluations/results` | 评估结果 |

## 数据与评估

数据统一放在 `/home/work/worktowork/data`。当前产品口径只保留 A 股专项数据集：

- `ashare_announcement`：公告检索与证据召回。
- `ashare_financial_fact`：年报财务事实与数值一致性。
- `ashare_market_sentiment`：市场情绪和热度解释。
- `ashare_daily_brief`：每日简报排序、覆盖和缺失原因。

评估维度：

- 响应质量：检索命中、证据召回、事实 grounding、数值准确率、拒答准确率。
- 轨迹状态：预期路径匹配、工具组召回、异常工具调用、verifier 修复率。
- 效率与稳定性：端到端延迟、节点耗时、token 使用、失败类型、告警事件。

## 环境变量

| 变量 | 说明 |
| --- | --- |
| `DATABASE_URL` | SQLite 路径 |
| `REDIS_URL` | Redis 地址 |
| `DATA_DIR` | 数据根目录 |
| `PUBLIC_DATA_DIR` | 公开数据缓存目录 |
| `CHAT_PROVIDER` / `CHAT_API_KEY` / `CHAT_API_BASE` / `CHAT_MODEL` | Chat provider 配置 |
| `EMBEDDING_PROVIDER` / `EMBEDDING_MODEL` | Embedding provider 配置 |
| `AUTH_SECRET` | HTTP-only JWT cookie 签名密钥 |
| `ASHARE_DAILY_SYNC_ENABLED` | 是否启用后端日更 scheduler，默认 `true` |
| `ASHARE_DAILY_SYNC_HOUR` | A 股日更小时，默认 `3`，按 Asia/Shanghai 计算 |
| `TUSHARE_TOKEN` | 可选，TuShare provider 令牌 |

## 验证命令

```bash
cd /home/work/worktowork/workspace
set -a; source .env >/dev/null 2>&1; set +a

PYTHONPATH=backend /root/anaconda3/envs/agent-learning/bin/python -m pytest -s -q backend/tests/test_ashare_daily_brief.py backend/tests/test_finance_tool_routing.py backend/tests/test_finance_connectors.py
PYTHONPATH=backend /root/anaconda3/envs/agent-learning/bin/python -m compileall -q backend/app

cd frontend
PATH=/root/.nvm/versions/node/v22.20.0/bin:$PATH npm run build
```

最近一次验证结果：

- 后端 A 股核心测试：`17 passed`
- 前端构建：`npm run build` 通过
- Docker 重建：`docker compose up -d --build backend worker frontend` 可启动

## 项目边界

- 只使用公开或可替换的数据源 provider。
- MCP 作为受控 provider 接入，不允许 Agent 任意调用外部工具。
- 缺少公告、年报或结构化财务事实时，只展示热度、关注、市场情绪和数据覆盖状态等弱信号。
- 弱信号不替代财务事实，不推导估值、收入利润变化或交易结论。
