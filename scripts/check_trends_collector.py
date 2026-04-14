import argparse
import asyncio
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.collectors.trends_collector import GoogleTrendsCollector, TrendsCollectorError


async def _run(args: argparse.Namespace) -> int:
    collector = GoogleTrendsCollector(
        headless=not args.show_browser,
        proxy=args.proxy,
        language=args.language,
        timeout_ms=args.timeout_ms,
    )
    await collector.start()
    try:
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
    parser = argparse.ArgumentParser(description="Run a direct Google Trends collector smoke test.")
    parser.add_argument("--base-keyword", default="openai")
    parser.add_argument("--keywords", nargs="+", default=["chatgpt", "gpt-4"])
    parser.add_argument("--time-range", default="today 12-m")
    parser.add_argument("--geo", default="")
    parser.add_argument("--language", default="en-US")
    parser.add_argument("--timezone-offset", type=int, default=0)
    parser.add_argument("--timeout-ms", type=int, default=45000)
    parser.add_argument("--proxy", default=None)
    parser.add_argument("--show-browser", action="store_true")
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
