# PubSpy API

本文档面向前端、集成方和运维同学，说明 `PubSpy` 相关接口的用途、调用顺序，以及和 `SiteData` 持久化浏览器会话的默认集成方式。

## Overview

当前提供 3 个接口：

1. `POST /api/pubspy/analyze`
用途：分析目标站点，提取 `pub id`、`ads.txt`、当前域名流量/WHOIS，并可选补充 `top keywords`

2. `POST /api/pubspy/related-domains`
用途：根据 `pub id` 查询同一 AdSense 体系下的关联域名

3. `POST /api/pubspy/domain-metrics`
用途：批量补充域名的流量和 WHOIS 信息

## 默认浏览器行为

`PubSpy` 里的 `top keywords` 补充并不是自己单独抓取，而是复用 `SiteData` 的流量采集能力。

从当前版本开始，默认行为已经切到持久化 `CDP` 会话：

- `keyword_collection_mode` 默认是 `browser`
- 如果请求里不手动传 `keyword_browser_cdp_url`，会自动读取 `.env` 里的默认浏览器配置
- 当前默认配置是：

```env
TREND_BROWSER_MODE=cdp
TREND_BROWSER_CDP_URL=http://127.0.0.1:9333
TREND_BROWSER_USER_DATA_DIR=/home/luolink/.cache/adssearch/sitedata-chrome-profile
BROWSER_MANUAL_LOGIN_URL=http://192.168.0.4:6080/vnc.html
```

这意味着：

- 前端或调用方通常不需要再传 `keyword_browser_cdp_url`
- `PubSpy analyze` 在 `include_top_keywords=true` 时，会默认走同一条已登录、已验证的浏览器会话
- 如果 `SiteData` 的 Google 登录态或 `cf_token` 失效，只需要在同一个 noVNC 窗口里重新验证一次

当前默认入口：

- `CDP`: `http://127.0.0.1:9333`
- `noVNC`: `http://192.168.0.4:6080/vnc.html`
- `profile_dir`: `/home/luolink/.cache/adssearch/sitedata-chrome-profile`

## 1. Analyze API

### Endpoint

```http
POST /api/pubspy/analyze
Content-Type: application/json
```

### 主要能力

- 规范化目标域名
- 抓页面提取 `pub id`
- 读取 `ads.txt`
- 补充当前域名流量和 WHOIS
- 可选查询关联域名
- 可选提取外链域名
- 可选通过 `SiteData` 补充 `top keywords`

### 推荐请求

如果你希望直接复用默认持久化浏览器会话，通常只需要这样传：

```json
{
  "url": "image2url.com",
  "include_related_domains": true,
  "include_outbound_domains": false,
  "enrich_current_domain": true,
  "include_top_keywords": true
}
```

说明：

- 这里没有显式传 `keyword_browser_cdp_url`
- 只要 `.env` 里的默认 `CDP` 会话可用，`top keywords` 会自动走浏览器路径

### 什么时候还需要手动传浏览器参数

这些场景才建议手动覆盖默认配置：

- 你要切到另一台 Chrome/CDP 会话
- 你想强制走 `direct`
- 你在本地开发机上用另一份 profile 调试

示例：

```json
{
  "url": "image2url.com",
  "include_top_keywords": true,
  "keyword_collection_mode": "browser",
  "keyword_browser_mode": "cdp",
  "keyword_browser_cdp_url": "http://127.0.0.1:9222"
}
```

### 响应重点字段

- `normalized_domain`
- `page_url`
- `pub_id`
- `pub_id_display`
- `pub_id_source`
- `ads_txt`
- `current_domain.traffic`
- `current_domain.whois`
- `current_domain.top_keywords`
- `related_domains`
- `outbound_domains`
- `warnings`

### 响应示例

```json
{
  "normalized_domain": "image2url.com",
  "pub_id": "pub-5177457324079072",
  "pub_id_display": "ca-pub-5177457324079072",
  "pub_id_source": "html",
  "current_domain": {
    "domain": "image2url.com",
    "is_current": true,
    "traffic": {
      "domain": "image2url.com",
      "status": "success",
      "formatted": "679,362",
      "monthly_visits": 679362,
      "traffic_month": "2026-03-01",
      "source": "traffic_api"
    },
    "whois": {
      "registrar": "NameCheap, Inc.",
      "created_date": "2025-07-09T16:25:58Z",
      "expires_date": "2026-07-09T16:25:58Z"
    },
    "top_keywords": [
      {
        "keyword": "image to url",
        "volume": 20890,
        "cpc": 0.43,
        "estimated_value": 17600
      }
    ]
  },
  "warnings": []
}
```

## 2. Related Domains API

### Endpoint

```http
POST /api/pubspy/related-domains
Content-Type: application/json
```

### 请求示例

```json
{
  "pub_id": "pub-5177457324079072",
  "current_domain": "image2url.com",
  "include_enrichment": true,
  "max_domains": 10
}
```

### 说明

- `include_enrichment=true` 时，会继续补充这些关联域名的流量和 WHOIS
- 这里的流量补充走 `PubSpy` 自己的 worker 链路，不依赖 `SiteData`
- `top keywords` 目前只在 `/api/pubspy/analyze` 的当前域名增强中补

## 3. Domain Metrics API

### Endpoint

```http
POST /api/pubspy/domain-metrics
Content-Type: application/json
```

### 请求示例

```json
{
  "domains": [
    "image2url.com",
    "tiktokwrapped.app"
  ]
}
```

### 说明

- 用于批量查域名流量和 WHOIS
- 不负责抓页面，也不负责 `top keywords`

## 推荐调用顺序

最常见的前端联调顺序：

1. 先调 `POST /api/pubspy/analyze`
2. 如果需要 `top keywords`，直接把 `include_top_keywords` 设为 `true`
3. 如果需要同 pub 站点，再调 `POST /api/pubspy/related-domains`
4. 如果需要补额外一组域名指标，再调 `POST /api/pubspy/domain-metrics`

## 浏览器会话失效时怎么处理

如果 `analyze` 的 `warnings` 里出现和 `top keywords` 相关的失败信息，优先检查默认浏览器会话。

推荐排查顺序：

1. 打开 `http://192.168.0.4:6080/vnc.html`
2. 看当前持久化 profile 里的 Google 登录态是否还在
3. 如果 SiteData 要求真人验证，在同一个窗口里重新完成验证
4. 调 `POST /api/sitedata/browser-health` 确认 `status=healthy`
5. 再重新调用 `POST /api/pubspy/analyze`

### 管理员处理要求

如果默认浏览器会话失效，例如出现下面这些情况：

- `browser-health` 返回 `needs_manual_login`
- `has_user_info=false`
- `has_cf_token=false`
- `PubSpy analyze` 的 `warnings` 里出现 `Top keyword enrichment failed`

需要让管理员立即处理，不要让前端或普通调用方自己兜底。

管理员应立即执行：

1. 打开 `http://192.168.0.4:6080/vnc.html`
2. 在持久化 profile 对应的浏览器窗口里重新登录 Google
3. 如有 SiteData/Cloudflare 真人验证，立即完成验证
4. 重新调用 `POST /api/sitedata/browser-health`，确认恢复到 `status=healthy`
5. 再通知调用方继续联调或重试请求

更详细的浏览器会话说明见：

- [sitedata-persistent-session.md](./sitedata-persistent-session.md)
- [sitedata-api.md](./sitedata-api.md)
