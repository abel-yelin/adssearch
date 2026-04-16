# Google Trends 免费扫词服务开发说明

## 1. 目标

本文档记录项目内“Google Trends 免费每日挖词服务”的实现细节。这个功能是独立于现有 FastAPI / Redis / PostgreSQL 趋势任务之外的第四个核心功能，目标是：

- 完全本地运行
- 不依赖付费 API
- 不依赖现有扩展的订阅校验
- 默认每天 `09:00 Asia/Shanghai` 自动运行
- 默认口径为：
  - `geo=US`
  - `time_range=now 7-d`
  - 单页比较 `5` 个词
  - 只保留 `related queries` 中的 `rising`
- 结果落本地 `SQLite + CSV + JSON`

第一版优先保证“稳定、免费、能长期跑”，不引入公网 API，不接入 Redis/PostgreSQL，不做复杂时间序列二次判定。

## 2. 代码位置

核心实现位于：

- [app/free_trends/config.py](/home/luolink/projects/adssearch/app/free_trends/config.py:1)
- [app/free_trends/normalize.py](/home/luolink/projects/adssearch/app/free_trends/normalize.py:1)
- [app/free_trends/storage.py](/home/luolink/projects/adssearch/app/free_trends/storage.py:1)
- [app/free_trends/collector.py](/home/luolink/projects/adssearch/app/free_trends/collector.py:1)
- [app/free_trends/service.py](/home/luolink/projects/adssearch/app/free_trends/service.py:1)
- [app/free_trends/scheduler.py](/home/luolink/projects/adssearch/app/free_trends/scheduler.py:1)

运行入口：

- 单次执行：[scripts/run_free_trends_once.py](/home/luolink/projects/adssearch/scripts/run_free_trends_once.py:1)
- 常驻调度：[scripts/run_free_trends_service.py](/home/luolink/projects/adssearch/scripts/run_free_trends_service.py:1)
- 示例配置：[config/free_trends_service.example.json](/home/luolink/projects/adssearch/config/free_trends_service.example.json:1)

测试：

- [tests/test_free_trends_service.py](/home/luolink/projects/adssearch/tests/test_free_trends_service.py:1)

## 3. 架构概览

整体链路如下：

```text
JSON config
  -> FreeTrendsConfig
  -> DailyTrendsDiscoveryService
     -> SQLite storage
     -> Playwright persistent collector
     -> in-memory BFS queue
     -> JSON / CSV outputs
     -> status file
```

模块职责：

- `config.py`
  负责读取 JSON 配置并准备目录。

- `normalize.py`
  负责关键词标准化和去重键生成。

- `storage.py`
  负责 SQLite 初始化、seed 管理、run/batch 日志、discovered terms 落库。

- `collector.py`
  负责访问 Google Trends compare/explore 页面，抓取 `related queries -> rising`。

- `service.py`
  负责单次运行的编排，包括批次推进、失败重试、递归队列、落盘输出。

- `scheduler.py`
  负责将服务挂到 `APScheduler` 的每日 cron 触发器。

## 4. 配置设计

配置模型定义在 [config.py](/home/luolink/projects/adssearch/app/free_trends/config.py:1)。

当前支持的主要字段：

- `timezone`
- `schedule_time`
- `geo`
- `time_range`
- `search_type`
- `language`
- `batch_size`
- `max_batches_per_run`
- `max_depth`
- `retry_limit`
- `max_consecutive_failures`
- `cooldown_hours`
- `output_dir`
- `database_path`
- `status_file`
- `log_file`
- `root_terms`
- `browser_headless`
- `browser_channel`
- `browser_executable_path`
- `browser_user_data_dir`
- `request_timeout_ms`

默认推荐值：

```json
{
  "timezone": "Asia/Shanghai",
  "schedule_time": "09:00",
  "geo": "US",
  "time_range": "now 7-d",
  "batch_size": 5,
  "max_batches_per_run": 20,
  "max_depth": 2,
  "retry_limit": 3,
  "max_consecutive_failures": 5
}
```

说明：

- `batch_size` 固定建议为 `5`，因为 Google Trends compare 页面一次最多比较 5 个词。
- `max_depth=0` 表示只扫 root pool，不递归。
- `max_depth>0` 时，新发现的 rising 词会进入下一轮队列。
- `browser_user_data_dir` 是稳定性的关键。实测复用已有 Chrome profile 比新建空 profile 更稳定。

## 5. 关键词标准化

实现位于 [normalize.py](/home/luolink/projects/adssearch/app/free_trends/normalize.py:1)。

处理规则：

- 去掉隐藏字符，例如 `\u200b`
- 折叠连续空格
- 去掉首尾空白
- 去重键使用 `casefold()` 后的小写标准化结果

示例：

- `"  Voice   Generator\u200b "` -> `"Voice Generator"`
- 去重键 -> `"voice generator"`

这样可以避免：

- 大小写重复
- 不同空格格式重复
- 从 Google Trends 返回的文本和配置种子之间匹配不一致

## 6. SQLite 设计

实现位于 [storage.py](/home/luolink/projects/adssearch/app/free_trends/storage.py:1)。

### 6.1 `seed_terms`

用于保存 root pool 的状态。

字段：

- `normalized_term`
- `term`
- `enabled`
- `cooldown_until`
- `last_scanned_at`
- `last_status`
- `created_at`
- `updated_at`

作用：

- 保存原始种子词
- 控制冷却
- 记录最近是否扫描过、是否被封锁

### 6.2 `runs`

用于记录每次日扫任务。

字段：

- `run_id`
- `started_at`
- `finished_at`
- `status`
- `new_keyword_count`
- `output_json_path`
- `output_csv_path`
- `latest_csv_path`
- `error_message`

状态目前主要有：

- `running`
- `completed`
- `blocked`

### 6.3 `run_batches`

用于记录每一批 compare 页请求。

字段：

- `batch_id`
- `run_id`
- `batch_no`
- `keywords_json`
- `status`
- `retry_count`
- `new_discoveries_count`
- `error_type`
- `error_message`
- `started_at`
- `finished_at`

### 6.4 `discovered_terms`

用于保存当次运行发现的 rising 词。

字段：

- `run_id`
- `normalized_term`
- `term`
- `source_term`
- `source_terms_json`
- `depth`
- `discovered_at`
- `batch_id`
- `region`
- `time_range`
- `trend_type`
- `value_label`

唯一键：

- `(run_id, normalized_term)`

设计原因：

- 同一个 rising 词在同一轮运行里可能从多个 source term 出现
- 第一版只保留一条主记录，但会把多个来源写入 `source_terms_json`

## 7. 抓取策略

### 7.1 页面模式

当前实现使用 Playwright 的 `launch_persistent_context()`，复用浏览器用户目录。

实现位于 [collector.py](/home/luolink/projects/adssearch/app/free_trends/collector.py:1)。

主要参数：

- `headless`
- `browser_channel`
- `browser_executable_path`
- `browser_user_data_dir`
- `language`
- `timeout_ms`

为什么使用 persistent mode：

- 降低反复初始化浏览器的开销
- 更容易复用 Cookie 和已有浏览器状态
- 实测比空白临时 profile 更不容易立刻触发 `HTTP 429`

### 7.2 Compare 页面构造

当前使用：

```text
https://trends.google.com/trends/explore?date=<time_range>&q=<comma-separated keywords>&geo=<geo>&hl=en-US
```

批次组装规则：

- 每批最多 `5` 个词
- 同一个 compare 页面只处理一批
- 不开 5 个独立 tab

### 7.3 网络接口优先

优先通过响应监听抓：

- `/trends/api/widgetdata/relatedsearches`

解析逻辑：

1. 从 URL 的 `req` 参数里反查当前关键词
2. 解析 Google 的 JSON 前缀格式 `)]}',`
3. 从 `rankedList` 中优先取 rising 列表
4. 抽取：
   - `query`
   - `value` -> 存成 `value_label`

如果 `value` 是数值，保存为：

- `4500` -> `+4,500%`

如果 `value` 是字符串，保存为：

- `Breakout`

### 7.4 DOM fallback

这是为了兼容：

- 新 Explore UI
- 中文界面
- 网络接口未命中但页面已经渲染出“相关查询”

实现位于 [collector.py](/home/luolink/projects/adssearch/app/free_trends/collector.py:1) 的：

- `_capture_dom_fallback()`
- `_scroll_for_dom_sections()`
- `_parse_dom_related_queries()`

当前支持的 DOM 文案：

- `Related queries`
- `相关查询`
- `Rising`
- `搜索量上升`
- `Top`
- `热门`
- `Breakout`
- `飙升`
- `+4,100%`
- `当前显示的是第 1-5 个查询（共 16 个）`

这部分是这次打通流程的关键修正。之前仅依赖网络接口时，`image` 在复用已有 profile 后不再 429，但会超时拿不到 `related queries`。补上 DOM fallback 后，`image` 和 `ai` 都成功抓到了真实值。

### 7.5 为什么允许 new Explore UI

当前 free service 不再强制要求 classic explore 一定成功。逻辑是：

- 先尝试切回 classic
- 切不回时不直接失败
- 继续依赖 DOM fallback 解析页面正文

这和原有 `trends_collector.py` 的队列任务实现不同。独立服务更偏重“本地稳定跑出结果”，所以容错优先级更高。

## 8. 单次运行编排

实现位于 [service.py](/home/luolink/projects/adssearch/app/free_trends/service.py:1)。

单次运行流程：

1. 将 `root_terms` upsert 到 `seed_terms`
2. 读取当前未冷却种子词
3. 构造内存队列 `deque[QueueItem]`
4. 每轮取最多 `5` 个词
5. 创建 `run_batches` 记录
6. 进入重试循环
7. 调 `collector.collect_batch()`
8. 将 rising 词写入 `discovered_terms`
9. 如果允许递归，则把新词推回队列
10. 批次之间随机 sleep
11. 结束后写 JSON / CSV / latest CSV
12. 更新 `runs` 和 `status_file`

### 8.1 递归策略

当前使用轻量 BFS：

- 队列元素：`QueueItem(term, depth, source_term)`
- 去重集合：`seen_terms`
- 只要 `depth + 1 <= max_depth`，就会把新词加入队列

这意味着：

- `max_depth=0`：只跑 root terms
- `max_depth=1`：root -> rising
- `max_depth=2`：root -> rising -> rising of rising

### 8.2 失败处理

每批最多重试 `retry_limit` 次。

异常分类：

- `TrendsBlockedError`
  - 典型场景：`HTTP 429`、验证码、unusual traffic
  - 当前批次直接 `blocked`
  - 对相关 seed term 打冷却
  - 整轮运行以 `blocked` 结束

- `TrendsCollectionError`
  - 典型场景：超时、页面未出现 related queries
  - 指数退避后重试
  - 连续失败超阈值后结束当日任务

### 8.3 冷却逻辑

当 Google 明确风控时：

- 使用 `cool_down_seed_terms()`
- 设置 `cooldown_until = now + cooldown_hours`

下一轮读取 available seeds 时会跳过这些词。

## 9. 输出设计

输出目录按日期分组：

```text
<output_dir>/
  YYYY-MM-DD/
    <run_id>.json
    <run_id>.csv
  latest_hot_keywords.csv
  service_status.json
  service.log
  free_trends.db
```

### 9.1 JSON

保存结构化全量结果，包含：

- `run_id`
- `generated_at`
- `geo`
- `time_range`
- `trend_type`
- `items`

每个 item 包含：

- `term`
- `normalized_term`
- `source_term`
- `source_terms`
- `depth`
- `discovered_at`
- `batch_id`
- `region`
- `time_range`
- `trend_type`
- `value_label`

### 9.2 CSV

保存扁平化结果，方便人工筛选。

字段：

- `term`
- `normalized_term`
- `source_term`
- `source_terms`
- `depth`
- `discovered_at`
- `batch_id`
- `region`
- `time_range`
- `trend_type`
- `value_label`

### 9.3 status file

`status_file` 保存最近一次运行摘要，便于外部只读监控。

当前包含：

- `run_id`
- `status`
- `started_at`
- `finished_at`
- `new_keyword_count`
- `output_paths`
- `blocked_message`

## 10. 调度设计

实现位于 [scheduler.py](/home/luolink/projects/adssearch/app/free_trends/scheduler.py:1)。

使用：

- `BackgroundScheduler`
- `CronTrigger`

规则：

- 每天 `09:00`
- 时区 `Asia/Shanghai`

常驻入口：

```bash
.venv/bin/python scripts/run_free_trends_service.py --config config/free_trends_service.example.json
```

单次入口：

```bash
.venv/bin/python scripts/run_free_trends_once.py --config config/free_trends_service.example.json
```

## 11. 实测结果

以下结果均在 `2026-04-16` 本地环境中完成。

### 11.1 `image`

首次使用独立新 profile：

- 触发 `HTTP 429`
- 说明空 profile 下风控风险较高

切到已有 Chrome profile：

- 使用 profile：`/home/luolink/.cache/adssearch-chrome-debug`
- 网络接口未稳定返回 related queries
- DOM fallback 成功抓到结果

真实抓到的值：

- `image of trump as jesus` -> `Breakout`
- `romoser nasa image claims` -> `Breakout`
- `trump ai image jesus` -> `Breakout`
- `trump as jesus image` -> `Breakout`
- `trump jesus image` -> `Breakout`

输出文件：

- [/tmp/free_trends_image_existing_profile_output/2026-04-16/20260416T004857Z-279679a7.json](/tmp/free_trends_image_existing_profile_output/2026-04-16/20260416T004857Z-279679a7.json)
- [/tmp/free_trends_image_existing_profile_output/2026-04-16/20260416T004857Z-279679a7.csv](/tmp/free_trends_image_existing_profile_output/2026-04-16/20260416T004857Z-279679a7.csv)

### 11.2 `ai`

同样使用已有 Chrome profile。

真实抓到的值：

- `allbirds ai` -> `+4,500%`
- `allbirds shoes ai` -> `+4,900%`
- `newbird ai` -> `+2,300%`
- `trump ai picture` -> `+2,900%`
- `trump jesus ai` -> `Breakout`

输出文件：

- [/tmp/free_trends_ai_existing_profile_output/2026-04-16/20260416T005143Z-dc7c81bc.json](/tmp/free_trends_ai_existing_profile_output/2026-04-16/20260416T005143Z-dc7c81bc.json)
- [/tmp/free_trends_ai_existing_profile_output/2026-04-16/20260416T005143Z-dc7c81bc.csv](/tmp/free_trends_ai_existing_profile_output/2026-04-16/20260416T005143Z-dc7c81bc.csv)

结论：

- 这条链路已经真实跑通
- 复用已有 profile 明显优于空白 profile
- DOM fallback 是当前稳定性的重要组成部分

## 12. 测试覆盖

测试文件在 [tests/test_free_trends_service.py](/home/luolink/projects/adssearch/tests/test_free_trends_service.py:1)。

当前覆盖：

- 配置读取
- 关键词标准化
- 批次组装
- rising rankedList 解析
- 中文 new Explore UI DOM 解析
- 去重与多来源保留
- 递归队列推进
- 调度时间
- 输出文件生成
- blocked/cooldown
- 10 词根冒烟

运行方式：

```bash
.venv/bin/pytest -q tests/test_free_trends_service.py
```

全量测试：

```bash
.venv/bin/pytest -q
```

当前项目内全量测试已通过：`57 passed`

## 13. 已知限制

### 13.1 仍然受 Google 风控影响

即使使用 persistent profile，也不能完全避免：

- `HTTP 429`
- captcha
- unusual traffic

当前策略是识别后冷却，而不是硬顶着刷。

### 13.2 DOM fallback 依赖页面文案

虽然已经支持：

- 英文
- 中文
- classic/new explore 常见文案

但如果 Google 改版严重，仍可能需要更新解析规则。

### 13.3 第一版不做分页

当前只抓页面当前能拿到的 related queries 列表，不主动点击下一页。

如果以后需要完整抓满：

- `1-5`
- `6-10`
- `11-15`

可以继续补翻页逻辑。

### 13.4 第一版不做二次判定

当前“热词”定义完全来自 Google Trends 的 `rising`：

- `Breakout`
- `+N%`

还没有叠加：

- 最近 7 天斜率
- 历史基线对比
- 多日连续性判断

这是有意为之，目的是先保证免费版能稳定跑。

## 14. 推荐运行方式

### 14.1 先单次验证

```bash
.venv/bin/python scripts/run_free_trends_once.py --config config/free_trends_service.example.json
```

### 14.2 再常驻运行

```bash
.venv/bin/python scripts/run_free_trends_service.py --config config/free_trends_service.example.json
```

### 14.3 优先复用已有浏览器 profile

推荐：

```text
$HOME/.cache/adssearch-chrome-debug
```

不推荐长期用空白新 profile，因为实测更容易被 Google Trends 立刻限流。

## 15. 后续可扩展方向

- 支持翻页抓完整 related queries
- 支持多地区
- 支持 `search_type` 切换
- 支持更细的冷却策略
- 支持运行结果对比和增量报告
- 支持极简本地状态 HTTP 端点
- 支持把 `latest_hot_keywords.csv` 自动喂给下一阶段流程
