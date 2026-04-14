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

### 响应示例
```json
{
  "success": true,
  "task_id": "a1b2c3d4",
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
  schemas/
    search.py
  services/
    scraper.py
  main.py
tests/
  test_health.py
```

- `app/main.py` 负责创建 FastAPI 应用
- `app/core/config.py` 放应用配置
- `app/api/router.py` 统一注册 API 路由
- `app/api/routes/` 放接口路由
- `app/schemas/` 放请求和响应模型
- `app/services/scraper.py` 放广告抓取核心逻辑
- `tests/` 放基础接口测试

## 新入口

项目现在只使用下面这个入口：

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

如果你之前使用过 `uvicorn main:app`，现在需要切换到新入口。
