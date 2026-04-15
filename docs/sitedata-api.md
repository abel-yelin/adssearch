# SiteData API

本文档面向前端、集成方和运维同学，说明 `SiteData` 相关接口的用途、调用方式、返回结构，以及浏览器登录态失效时的处理流程。

## Overview

当前提供 2 个接口：

1. `POST /api/sitedata/traffic`
用途：获取站点流量数据

2. `POST /api/sitedata/browser-health`
用途：检查浏览器会话是否仍然具备可用的登录态、`cf_token` 和采集能力

## 1. Traffic API

### Endpoint

```http
POST /api/sitedata/traffic
Content-Type: application/json
```

### Collection Modes

支持两种采集方式：

- `direct`
说明：直接请求 `traffic.sitedata.dev`

- `browser`
说明：复用真实浏览器会话，打开 `sitedata.dev` 页面并点击 `Analyze`

### When To Use `direct`

适合这些场景：

- 目标域名不依赖登录态
- 上游不会返回 `Unauthorized clientId`
- 需要快速批量采集

示例：

```json
{
  "domain": "chatgpt.com",
  "collection_mode": "direct",
  "timeout_seconds": 30,
  "proxy": null
}
```

### When To Use `browser`

适合这些场景：

- 目标域名在 `direct` 模式下返回 `Unauthorized clientId`
- 需要复用浏览器中的 `userInfo`
- 需要复用 `cf_token`
- 页面需要 Cloudflare 或其他真人验证后才能出数

示例：

```json
{
  "domain": "www.image2url.com",
  "collection_mode": "browser",
  "browser_mode": "cdp",
  "browser_cdp_url": "http://127.0.0.1:9222",
  "browser_headless": false,
  "browser_pre_click_wait_ms": 5000,
  "browser_post_click_wait_ms": 10000
}
```

### Browser Parameters

常用浏览器字段：

- `browser_mode`
可选值：`isolated`、`cdp`、`persistent`

- `browser_cdp_url`
用于 `cdp` 模式，例如 `http://127.0.0.1:9222`

- `browser_user_data_dir`
用于 `persistent` 模式，指定固定 Chrome profile

- `browser_headless`
是否无头运行

- `browser_pre_click_wait_ms`
点击 `Analyze` 前等待时间

- `browser_post_click_wait_ms`
点击 `Analyze` 后等待时间

### Response Fields

成功时主要返回：

- `requested_domain`
- `resolved_domain`
- `collection_mode`
- `site_name`
- `title`
- `description`
- `snapshot_date`
- `global_rank`
- `category_rank`
- `monthly_visits`
- `traffic_sources`
- `top_keywords`
- `top_countries`
- `engagements`
- `browser_debug`

说明：

- `resolved_domain` 可能与输入不同，例如从 `www.image2url.com` 回退到 `image2url.com`
- `browser_debug` 仅在 `browser` 模式下返回
- `browser_debug` 已做脱敏，不会原样返回 `clientId`、`sign`、`cf_token`

### Response Example

```json
{
  "requested_domain": "www.image2url.com",
  "resolved_domain": "image2url.com",
  "collection_mode": "browser",
  "site_name": "image2url.com",
  "snapshot_date": "2026-03-01T00:00:00+00:00",
  "monthly_visits": [
    { "month": "2026-01-01", "visits": 216948 },
    { "month": "2026-02-01", "visits": 434893 },
    { "month": "2026-03-01", "visits": 679362 }
  ],
  "traffic_sources": [
    { "source": "Search", "share_percent": 53.44 },
    { "source": "Direct", "share_percent": 33.3 }
  ],
  "top_keywords": [
    { "keyword": "image to url", "volume": 20890, "cpc": 0.43, "estimated_value": 17600 }
  ],
  "top_countries": [
    { "country_code": "US", "share_percent": 30.87 }
  ],
  "engagements": {
    "Visits": "679362",
    "TimeOnSite": "122.47499103426671",
    "PagePerVisit": "3.4776303883682718"
  },
  "browser_debug": {
    "request_count": 2
  }
}
```

## 2. Browser Health API

### Endpoint

```http
POST /api/sitedata/browser-health
Content-Type: application/json
```

### Purpose

这个接口用于回答以下问题：

- 当前浏览器里是否还有 `userInfo`
- 当前浏览器里是否还有 `cf_token`
- 最近一次浏览器采集是否可用
- 现在是否需要人工重新登录

### Request Example

```json
{
  "probe_domain": "verifieddr.com",
  "browser_mode": "cdp",
  "browser_cdp_url": "http://127.0.0.1:9222",
  "browser_headless": false
}
```

### Response Fields

- `probe_domain`
- `browser_mode`
- `current_url`
- `has_user_info`
- `has_cf_token`
- `has_anon_client_id`
- `last_browser_collection_usable`
- `requires_manual_login`
- `status`
- `failure_code`
- `message`
- `recommended_action`
- `manual_login_url`
- `manual_login_steps`
- `request_count`
- `recent_console`

### Status Meanings

- `healthy`
说明：浏览器会话可直接用于 `browser` 模式采集

- `needs_manual_login`
说明：浏览器缺少登录态、`cf_token` 或真人验证状态，需要你先手动处理

- `browser_error`
说明：更像是浏览器连接、配置或页面行为异常，不一定是登录态问题

### Response Example

```json
{
  "probe_domain": "verifieddr.com",
  "browser_mode": "cdp",
  "current_url": "https://sitedata.dev/traffic/verifieddr.com",
  "has_user_info": true,
  "has_cf_token": true,
  "has_anon_client_id": true,
  "last_browser_collection_usable": true,
  "requires_manual_login": false,
  "status": "healthy",
  "failure_code": null,
  "message": "Browser session is healthy and SiteData collection is currently usable.",
  "recommended_action": "No action needed. You can continue using the browser collector.",
  "manual_login_url": "http://192.168.0.4:6080/vnc.html",
  "manual_login_steps": [
    "Open the VNC browser session at the provided URL.",
    "If SiteData or Google asks you to sign in, complete the login in that browser window.",
    "If Cloudflare or another verification page appears, finish the manual verification there.",
    "Keep the same Chrome profile and browser window open, then rerun the health check or collection request."
  ],
  "request_count": 1,
  "recent_console": [
    "Refreshing traffic data with token: false"
  ]
}
```

## 3. Manual Login Flow

当 `requires_manual_login = true` 时，优先通过这个入口处理：

```text
http://192.168.0.4:6080/vnc.html
```

建议操作顺序：

1. 打开 VNC 页面。
2. 在同一个 Chrome profile 中访问 `sitedata.dev`。
3. 如果要求登录 Google 或 SiteData，在该窗口中完成。
4. 如果弹出 Cloudflare 或其他真人验证，也在该窗口中完成。
5. 不要更换 `user-data-dir`，也不要切到新的无状态浏览器 profile。
6. 完成后重新调用 `/api/sitedata/browser-health`。
7. 确认：

- `has_user_info = true`
- `has_cf_token = true`
- `last_browser_collection_usable = true`

8. 再调用 `/api/sitedata/traffic`

## 4. Recommended Call Sequence

推荐调用顺序：

1. 调 `/api/sitedata/browser-health`
2. 如果返回 `healthy`，直接调 `/api/sitedata/traffic`
3. 如果返回 `needs_manual_login`，先在 VNC 中完成登录或验证，再重新检查健康状态
4. 对无需浏览器状态的站点，可直接使用 `direct` 模式

## 5. Notes

- 并非所有域名都支持 `direct` 模式
- `browser` 模式依赖真实浏览器会话状态
- 长时间不用后，`userInfo`、`cf_token` 或 Cloudflare 验证状态可能失效
- 建议固定使用同一个 Chrome profile 和尽量稳定的网络出口
