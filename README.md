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
  }
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
  dependencies/services.py
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
```

- `app/main.py` 负责创建 FastAPI 应用
- `app/core/config.py` 放应用配置
- `app/core/logging.py` 放日志配置
- `app/core/middleware.py` 处理请求 ID 和请求日志
- `app/core/exceptions.py` 注册统一异常处理
- `app/api/router.py` 统一注册 API 路由
- `app/api/routes/` 放接口路由
- `app/dependencies/` 放依赖注入入口
- `app/schemas/` 放请求和响应模型
- `app/services/queue_service.py` 管理 Redis/RQ 队列连接
- `app/services/search_service.py` 放接口业务编排
- `app/services/task_service.py` 负责提交任务和查询任务状态
- `app/services/scraper.py` 放广告抓取核心逻辑
- `app/tasks/search_tasks.py` 是 worker 实际执行的任务函数
- `app/worker.py` 是队列 worker 启动入口
- `tests/` 放基础接口测试

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
```

如果你要传代理或其他敏感值，建议在部署平台或本机 shell 里注入，不要写入仓库。

## 测试

```bash
pytest -q
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
