# Google Ads Transparency Scraper API

## 快速开始

### 方法一：本地运行
```bash
pip install -r requirements.txt
playwright install chromium
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 方法二：Docker 部署
```bash
docker build -t ads-scraper-api .
docker run -p 8000:8000 ads-scraper-api
```

命令行快速测试任意域名广告投放：

```bash
.venv/bin/python scripts/check_ads_domain.py lovable.dev --max-scroll-pages 2 --pretty
```

## API 端点

### 健康检查
```
GET /api/health
```

### 域名查询
```
POST /api/search
Content-Type: application/json

{
  "domain": "aiimagetovideo.ai",
  "region": "anywhere",
  "max_scroll_pages": 10,
  "timeout": 30000
}
```

### 任务状态查询
```
GET /api/tasks/{task_id}
```

### Sitemap 监控
```
POST /api/sitemaps/monitors
Content-Type: application/json

{
  "site_url": "https://example.com",
  "sitemap_url": "https://example.com/sitemap_index.xml",
  "interval_minutes": 5,
  "enabled": true
}
```

```
GET /api/sitemaps/monitors
GET /api/sitemaps/monitors/{monitor_id}
POST /api/sitemaps/monitors/{monitor_id}/run
GET /api/sitemaps/runs/{run_id}
GET /api/sitemaps/monitors/{monitor_id}/recent-new-urls
```

Sitemap 监控支持：
- 自动识别 `sitemap.xml` / `sitemap_index.xml`
- 递归解析子 sitemap
- 处理 `.xml.gz` sitemap
- 优先使用 `ETag` / `Last-Modified` 做条件请求
- 对比快照得到新增 URL、删除 URL、`lastmod` 变化 URL
- 首次运行只建立基线，不把全量历史 URL 当作“新增”

### 取消任务
```
POST /api/tasks/{task_id}/cancel
```

### 重试任务
```
POST /api/tasks/{task_id}/retry
```

### Google Trends 任务
```
POST /api/trends/tasks
Content-Type: application/json

{
  "base_keyword": "openai",
  "seed_keywords": ["chatgpt", "gpt-4"],
  "time_range": "today 12-m",
  "threshold": 20,
  "max_keywords": 100,
  "geo": "",
  "language": "en-US",
  "timezone_offset": 0,
  "proxy": null
}
```

查询状态：
```
GET /api/trends/tasks/{task_id}
```

查询摘要：
```
GET /api/trends/tasks/{task_id}/summary
```

导出结果：
```
GET /api/trends/tasks/{task_id}/export
```

取消与重试：
```
POST /api/trends/tasks/{task_id}/cancel
POST /api/trends/tasks/{task_id}/retry
```

### 响应示例
```json
{
  "success": true,
  "task_id": "a1b2c3d4",
  "status": "queued",
  "message": "Search task submitted successfully."
}
```

任务完成后，`GET /api/tasks/{task_id}` 会返回：

```json
{
  "success": true,
  "task_id": "a1b2c3d4",
  "status": "finished",
  "result": {
    "success": true,
    "task_id": "worker-task",
    "data": {
      "query_domain": "aiimagetovideo.ai",
      "has_ads": true,
      "advertisers": [
        {
          "advertiser_id": "AR01888412131238346753",
          "name": "HAN HU",
          "url": "https://adstransparency.google.com/advertiser/AR01888412131238346753",
          "region": "",
          "matched_domains": ["aiimagetovideo.ai"],
          "other_domains": ["another-site.com", "brand.ai"],
          "has_query_domain": true
        }
      ],
      "all_domains": ["aiimagetovideo.ai", "another-site.com", "brand.ai"],
      "other_domains": ["another-site.com", "brand.ai"],
      "ad_creatives": [],
      "total_ads_found": 0
    },
    "duration_seconds": 45.32
  },
  "retries_left": 1
}
```

## 前端配置

在 Lovable 前端中，将 `API_BASE_URL` 设置为你部署的后端地址，例如：
- 本地开发：`http://localhost:8000`
- 生产部署：`https://your-server.com`

## 注意事项

- 查询通常需要 30s - 3min，取决于广告数量
- 建议部署在有稳定网络的服务器上
- 如果 Google 有反爬限制，可配置代理

## 项目结构

```bash
app/
  api/router.py
  api/routes/
    health.py
    search.py
  core/config.py
  core/exceptions.py
  core/logging.py
  core/middleware.py
  db/session.py
  models/search_task.py
  dependencies/services.py
  repositories/task_repository.py
  schemas/
    health.py
    search.py
  services/
    queue_service.py
    search_service.py
    task_service.py
    scraper.py
  tasks/search_tasks.py
  main.py
  worker.py
tests/
  conftest.py
  test_health.py
  test_search.py
docker-compose.yml
```

- `app/main.py` 负责创建 FastAPI 应用
- `app/core/config.py` 放应用配置
- `app/core/logging.py` 放日志配置
- `app/core/middleware.py` 处理请求 ID 和请求日志
- `app/core/exceptions.py` 注册统一异常处理
- `app/db/` 管理数据库连接和会话
- `app/models/` 放持久化模型
- `app/api/router.py` 统一注册 API 路由
- `app/api/routes/` 放接口路由
- `app/dependencies/` 放依赖注入入口
- `app/repositories/` 负责数据库读写
- `app/schemas/` 放请求和响应模型
- `app/services/queue_service.py` 管理 Redis/RQ 队列连接
- `app/services/search_service.py` 放接口业务编排
- `app/services/task_service.py` 负责提交任务和查询任务状态
- `app/services/scraper.py` 放广告抓取核心逻辑
- `app/tasks/search_tasks.py` 是 worker 实际执行的任务函数
- `app/worker.py` 是队列 worker 启动入口
- `tests/` 放基础接口测试
- `docker-compose.yml` 用于一键启动 api、worker、redis

## 新入口

项目现在只使用下面这个入口：

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

如果你之前使用过 `uvicorn main:app`，现在需要切换到新入口。

## 环境变量

支持这些非敏感配置项：

```bash
APP_ENV=development
APP_DEBUG=false
APP_VERSION=1.0.0
API_PREFIX=/api
ALLOW_ORIGINS=*
ALLOW_METHODS=*
ALLOW_HEADERS=*
ALLOW_CREDENTIALS=true
LOG_LEVEL=INFO
DEFAULT_REGION=anywhere
DEFAULT_TIMEOUT_MS=30000
DEFAULT_MAX_SCROLL_PAGES=10
REDIS_URL=redis://localhost:6379/0
QUEUE_NAME=adssearch
QUEUE_JOB_TIMEOUT=1800
QUEUE_RESULT_TTL=86400
QUEUE_FAILURE_TTL=86400
QUEUE_DEFAULT_RETRY_COUNT=1
DATABASE_URL=postgresql+psycopg2://adssearch:adssearch@localhost:5432/adssearch
SITEMAP_HTTP_TIMEOUT_SECONDS=30
SITEMAP_MAX_FILES=2000
SITEMAP_SCHEDULER_POLL_SECONDS=30
SITEMAP_SCHEDULER_BATCH_SIZE=20
```

如果你要传代理或其他敏感值，建议在部署平台或本机 shell 里注入，不要写入仓库。

## 测试

```bash
pytest -q
```

只验证 Google Trends 相关功能时，可以跑：

```bash
.venv/bin/python -m pytest tests/test_trends_collector.py tests/test_trend_tasks.py -q
```

## 异步运行

1. 启动 Redis
2. 启动 API：

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

3. 启动 Worker：

```bash
python -m app.worker
```

4. 启动 Sitemap Scheduler：

```bash
python -m app.sitemap_scheduler
```

## Google Trends 功能落地

### 直接验证采集器

这条命令会直接用 Playwright 访问 Google Trends，不经过 API 和队列：

```bash
.venv/bin/python scripts/check_trends_collector.py --base-keyword openai --keywords chatgpt gpt-4
```

### 通过 API 提交并轮询任务

先启动 API、Worker、Redis，再执行：

```bash
.venv/bin/python scripts/run_trend_task_demo.py --base-keyword openai --seed-keywords chatgpt gpt-4
```

### 常见问题

- 如果返回 `captcha_or_blocked` 或 `HTTP 429`，说明当前机器或代理 IP 被 Google Trends 限流。
- 采集器现在会明确识别 `429/403/captcha`，不会再把这类问题误报成普通超时。
- 真实环境建议配置稳定代理，并降低访问频率，否则很容易被 Google Trends 风控。

## Docker Compose

```bash
docker compose up --build
```

启动后：
- API: `http://localhost:8000`
- Redis: `localhost:6379`
- PostgreSQL: `localhost:5432`
- Worker: 在 Compose 内部自动启动
- Sitemap Scheduler: 在 Compose 内部自动启动

默认 PostgreSQL 连接：

```text
database: adssearch
username: adssearch
password: adssearch
```

## 持久化设计

- Redis/RQ：负责排队和分发任务
- PostgreSQL：负责持久化任务记录、状态和最终结果
- `GET /api/tasks/{task_id}` 优先返回数据库中的任务结果，不依赖 Redis 结果 TTL
