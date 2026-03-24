# Google Ads Transparency Scraper API

## 快速开始

### 方法一：本地运行
```bash
pip install -r requirements.txt
playwright install chromium
uvicorn main:app --host 0.0.0.0 --port 8000
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
    "advertisers": [
      {
        "advertiser_id": "AR01888412131238346753",
        "name": "HAN HU",
        "url": "https://adstransparency.google.com/advertiser/AR01888412131238346753",
        "region": ""
      }
    ],
    "all_domains": ["domain1.com", "domain2.ai"],
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
