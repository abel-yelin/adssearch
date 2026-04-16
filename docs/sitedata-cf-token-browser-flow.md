# SiteData `cf_token` 联调说明

本文档用于复现这条真实链路：

1. 启动一个可复用的 Chrome CDP 会话
2. 在 `sitedata.dev` 页面里完成 Cloudflare / Turnstile 验证
3. 让浏览器拿到 `localStorage.cf_token`
4. 再通过 FastAPI 的 `POST /api/sitedata/traffic` 查询真实流量

适用场景：

- `direct` 模式返回 `Unauthorized clientId`
- 目标域名必须先通过页面验证才能出数
- 需要复用浏览器中的 `cf_token`

典型例子：

- `image2url.com`

## 1. 前提条件

需要满足这些条件：

- 已安装项目依赖
- 本机可运行 Chromium / Chrome
- 可用 `xvfb-run`
- FastAPI 项目路径为当前仓库根目录

如果系统没有 Chrome，可以复用 Playwright 自带 Chromium。例如：

```bash
ls /home/luolink/.cache/ms-playwright/chromium-*/chrome-linux/chrome
```

## 2. 为什么 `direct` 不够

`/api/sitedata/traffic` 的 `direct` 模式只会直接请求：

```text
https://traffic.sitedata.dev/
```

这条链适合公开域名，例如：

- `chatgpt.com`
- `twitter.com`

但对一部分域名，上游会要求页面验证态。此时会出现：

```json
{
  "detail": {
    "code": "unauthorized_client",
    "message": "Unauthorized clientId"
  }
}
```

这时必须切换到：

- `collection_mode=browser`
- `browser_mode=cdp`

## 3. 启动可复用的 CDP 浏览器

推荐直接使用仓库自带脚本：

```bash
PORT=9333 \
CHROME_BIN=/home/luolink/.cache/ms-playwright/chromium-1140/chrome-linux/chrome \
USER_DATA_DIR=/tmp/adssearch-chrome-debug-headed \
START_URL='https://sitedata.dev/traffic/image2url.com' \
CHROME_EXTRA_ARGS='--no-sandbox' \
xvfb-run -a scripts/start_chrome_debug.sh
```

说明：

- `PORT=9333`
  用于 CDP 连接
- `USER_DATA_DIR`
  固定浏览器 profile，方便复用登录态和 `cf_token`
- `START_URL`
  直接打开目标域名流量页
- `xvfb-run -a`
  用虚拟桌面跑非 headless 浏览器
- `--no-sandbox`
  某些 Linux 环境里是必须的

启动成功后会看到类似输出：

```text
DevTools listening on ws://127.0.0.1:9333/devtools/browser/...
```

也可以确认 CDP 服务是否正常：

```bash
curl --noproxy '*' -sS http://127.0.0.1:9333/json/version
```

## 4. 先做浏览器健康检查

在正式抓流量前，先看当前会话是否已经有可用状态：

```bash
curl -X POST 'http://127.0.0.1:8000/api/sitedata/browser-health' \
  -H 'Content-Type: application/json' \
  -d '{
    "probe_domain": "image2url.com",
    "browser_mode": "cdp",
    "browser_cdp_url": "http://127.0.0.1:9333",
    "browser_headless": false,
    "browser_timeout_ms": 45000,
    "browser_pre_click_wait_ms": 2000,
    "browser_post_click_wait_ms": 8000
  }'
```

判断规则：

- `has_cf_token = true`
  说明当前 profile 已有 `cf_token`
- `last_browser_collection_usable = true`
  说明最近一次浏览器采集已经可用
- `status = healthy`
  可以直接调用流量接口
- `status = needs_manual_login`
  还需要人工验证

## 5. 获取 `cf_token`

### 方式 A：让页面自己完成验证

最推荐。

操作顺序：

1. 保持上一步启动的浏览器会话不要关闭
2. 打开 `https://sitedata.dev/traffic/image2url.com`
3. 点击页面上的 `Analyze`
4. 等待 Cloudflare / Turnstile 完成
5. 页面出现真实流量数据后，说明 `cf_token` 已写入当前 profile

成功后，页面通常会出现：

- `Monthly Visits`
- `Traffic Sources`
- `Top Keywords`
- `Top Traffic Regions`

### 方式 B：确认 `localStorage.cf_token`

如果要确认 token 是否已经落到浏览器里，可以复用同一个 CDP 会话检查：

```bash
/home/luolink/projects/adssearch/.venv/bin/python - <<'PY'
import asyncio, json
import requests
from playwright.async_api import async_playwright

async def main():
    ws_url = requests.get('http://127.0.0.1:9333/json/version', timeout=10).json()['webSocketDebuggerUrl']
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(ws_url)
        page = browser.contexts[0].pages[0]
        data = await page.evaluate("""() => ({
          local_keys: Object.keys(localStorage),
          has_cf_token: !!localStorage.getItem('cf_token'),
          has_anon_client_id: !!localStorage.getItem('anonClientId')
        })""")
        print(json.dumps(data, ensure_ascii=False, indent=2))
        await browser.close()

asyncio.run(main())
PY
```

期望输出：

```json
{
  "local_keys": ["firstReferer", "anonClientId", "cf_token", "nuxt-color-mode"],
  "has_cf_token": true,
  "has_anon_client_id": true
}
```

## 6. 调用 FastAPI 流量接口

确认浏览器已有 `cf_token` 后，再调用：

```bash
curl -X POST 'http://127.0.0.1:8000/api/sitedata/traffic' \
  -H 'Content-Type: application/json' \
  -d '{
    "domain": "image2url.com",
    "collection_mode": "browser",
    "browser_mode": "cdp",
    "browser_cdp_url": "http://127.0.0.1:9333",
    "browser_headless": false,
    "browser_timeout_ms": 45000,
    "browser_pre_click_wait_ms": 2000,
    "browser_post_click_wait_ms": 8000
  }'
```

成功时会返回结构化数据，例如：

```json
{
  "requested_domain": "image2url.com",
  "resolved_domain": "image2url.com",
  "collection_mode": "browser",
  "site_name": "image2url.com",
  "global_rank": 68408,
  "monthly_visits": [
    { "month": "2026-01-01", "visits": 216948 },
    { "month": "2026-02-01", "visits": 434893 },
    { "month": "2026-03-01", "visits": 679362 }
  ],
  "traffic_sources": [
    { "source": "Search", "share_percent": 53.44 },
    { "source": "Direct", "share_percent": 33.3 }
  ],
  "top_countries": [
    { "country_code": "US", "share_percent": 30.87 },
    { "country_code": "IN", "share_percent": 9.84 }
  ]
}
```

## 7. 推荐排查顺序

建议总是按这个顺序排：

1. 先试 `direct`
2. 如果返回 `Unauthorized clientId`，切 `browser + cdp`
3. 先查 `/api/sitedata/browser-health`
4. 如果 `has_cf_token=false`，先在页面里完成验证
5. 验证成功后，再查 `/api/sitedata/traffic`

## 8. 常见问题

### 1. `browser-health` 返回 `needs_manual_login`

说明当前会话还没有可用的 `cf_token`，或者 Cloudflare 验证没完成。

处理方式：

- 保持当前浏览器 profile
- 回到页面点 `Analyze`
- 等待流量区块真正渲染出来

### 2. `browser` 模式仍然返回 `verification_required`

通常说明：

- 用了新的浏览器 profile
- 换了新的 CDP 端口但没复用旧 profile
- Cloudflare 验证还没完成

优先检查：

- `USER_DATA_DIR` 是否还是原来的目录
- `browser_cdp_url` 是否连的是同一个浏览器

### 3. headless 模式拿不到 `cf_token`

这是常见现象。

建议：

- 优先使用 `xvfb-run + 非 headless Chromium`
- 不要默认依赖 `headless=true`

### 4. `chatgpt.com` 能查，`image2url.com` 不能查

这不是 FastAPI 本身故障，而是上游策略不同：

- `chatgpt.com` 可直接走 `direct`
- `image2url.com` 需要浏览器验证态

## 9. 复现成功的最小标准

满足以下 3 条，就说明链路打通了：

1. `/api/sitedata/browser-health` 返回 `has_cf_token=true`
2. 页面上能看到真实流量卡片，而不只是 `Analyze`
3. `/api/sitedata/traffic` 返回 `200` 且有 `monthly_visits`

## 10. 建议保留的会话参数

为了后续复现稳定，建议固定这些参数：

```text
PORT=9333
USER_DATA_DIR=/tmp/adssearch-chrome-debug-headed
browser_mode=cdp
browser_cdp_url=http://127.0.0.1:9333
browser_headless=false
```

这样同一个 profile 里的：

- `anonClientId`
- `cf_token`
- 其他浏览器状态

都可以稳定复用。
