import argparse
import asyncio
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings
from app.collectors.trends_collector import GoogleTrendsCollector, TrendsCollectorError


async def _run(args: argparse.Namespace) -> int:
    collector = GoogleTrendsCollector(
        headless=not args.show_browser,
        proxy=args.proxy,
        language=args.language,
        timeout_ms=args.timeout_ms,
        browser_mode=args.browser_mode,
        browser_cdp_url=args.browser_cdp_url,
        browser_executable_path=args.browser_executable_path,
        browser_user_data_dir=args.browser_user_data_dir,
        browser_channel=args.browser_channel,
        browser_extension_path=args.browser_extension_path,
    )
    try:
        await collector.start()
        result = await collector.capture(
            base_keyword=args.base_keyword,
            keywords=args.keywords,
            time_range=args.time_range,
            geo=args.geo,
            timezone_offset=args.timezone_offset,
        )
        print(
            json.dumps(
                {
                    "ok": True,
                    "base_keyword": args.base_keyword,
                    "keywords": args.keywords,
                    "time_range": args.time_range,
                    "related_queries_count": len(result["related_queries"]),
                    "raw_requests_count": len(result["raw_requests"]),
                    "related_keywords": [item.get("keyword", "") for item in result["related_queries"]],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except TrendsCollectorError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error_type": "TrendsCollectorError",
                    "code": exc.code,
                    "message": exc.message,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2
    finally:
        await collector.close()


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Run a direct Google Trends collector smoke test.")
    parser.add_argument("--base-keyword", default="openai")
    parser.add_argument("--keywords", nargs="+", default=["chatgpt", "gpt-4"])
    parser.add_argument("--time-range", default="today 12-m")
    parser.add_argument("--geo", default="")
    parser.add_argument("--language", default="en-US")
    parser.add_argument("--timezone-offset", type=int, default=0)
    parser.add_argument("--timeout-ms", type=int, default=45000)
    parser.add_argument("--proxy", default=settings.trend_default_proxy)
    parser.add_argument("--browser-mode", choices=["isolated", "cdp", "persistent"], default=settings.trend_browser_mode)
    parser.add_argument("--browser-cdp-url", default=settings.trend_browser_cdp_url)
    parser.add_argument("--browser-executable-path", default=settings.trend_browser_executable_path)
    parser.add_argument("--browser-user-data-dir", default=settings.trend_browser_user_data_dir)
    parser.add_argument("--browser-channel", default=settings.trend_browser_channel)
    parser.add_argument("--browser-extension-path", default=settings.trend_browser_extension_path)
    parser.add_argument("--show-browser", action="store_true")
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
