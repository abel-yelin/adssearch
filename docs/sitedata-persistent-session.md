# SiteData 持久化浏览器会话

这套脚本的目标是把下面 3 件事固定下来：

1. 固定 Chrome profile 目录
2. 固定 CDP 端口
3. 固定 noVNC 端口

这样你在 `http://<host>:6080/vnc.html` 里登录一次 Google，后面只要继续复用同一个 profile，`userInfo`、`cf_token` 和 SiteData 的浏览器态就能尽量保留下来。

## 启动

```bash
cd /home/luolink/projects/adssearch
bash scripts/start_sitedata_persistent_session.sh
```

默认值：

- `display`: `:100`
- `cdp`: `http://127.0.0.1:9333`
- `novnc`: `http://<host>:6080/vnc.html`
- `profile_dir`: `~/.cache/adssearch/sitedata-chrome-profile`
- `state_dir`: `~/.local/share/adssearch/sitedata-session`

## 停止

```bash
cd /home/luolink/projects/adssearch
bash scripts/stop_sitedata_persistent_session.sh
```

## 持久化关键点

- Google 登录状态保存在 `profile_dir`
- SiteData 的 `localStorage` 也保存在同一个 profile
- FastAPI 的 `browser + cdp` 采集要继续指向同一个 `CDP` 地址

推荐 `.env` 里保持：

```env
TREND_BROWSER_MODE=cdp
TREND_BROWSER_CDP_URL=http://127.0.0.1:9333
TREND_BROWSER_USER_DATA_DIR=/home/luolink/.cache/adssearch/sitedata-chrome-profile
BROWSER_MANUAL_LOGIN_URL=http://192.168.0.4:6080/vnc.html
```

## 常用检查

检查浏览器会话：

```bash
curl --noproxy '*' http://127.0.0.1:9333/json/version
```

检查 FastAPI 里的浏览器健康：

```bash
curl -X POST 'http://127.0.0.1:8000/api/sitedata/browser-health' \
  -H 'Content-Type: application/json' \
  -d '{
    "probe_domain": "image2url.com",
    "browser_mode": "cdp",
    "browser_cdp_url": "http://127.0.0.1:9333"
  }'
```

## 注意

- 如果你删掉 `profile_dir`，Google 登录状态和 `cf_token` 也会一起丢失
- 如果 SiteData 的验证过期了，重新打开 noVNC 在同一个 profile 里再过一遍验证即可
- `direct + sync token` 仍可能遇到上游限流，最稳的是优先使用 `browser + cdp`
