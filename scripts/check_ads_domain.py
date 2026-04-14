import argparse
import asyncio
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.scraper import GoogleAdsTransparencyScraper


async def _run(domain: str, region: str, max_scroll_pages: int, timeout: int, proxy: str | None) -> dict:
    scraper = GoogleAdsTransparencyScraper(
        headless=True,
        proxy=proxy,
        region=region,
        max_scroll_pages=max_scroll_pages,
        timeout=timeout,
    )
    await scraper.start()
    try:
        result = await scraper.search_domain(domain)
        return result.to_dict()
    finally:
        await scraper.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Query a domain in Google Ads Transparency Center.")
    parser.add_argument("domain", help="Domain to query, e.g. lovable.dev")
    parser.add_argument("--region", default="anywhere", help="Ads Transparency region")
    parser.add_argument("--max-scroll-pages", type=int, default=6, help="Max advertiser page scroll passes")
    parser.add_argument("--timeout", type=int, default=30000, help="Playwright timeout in milliseconds")
    parser.add_argument("--proxy", default=None, help="Optional proxy server")
    parser.add_argument("--pretty", action="store_true", help="Pretty print JSON")
    args = parser.parse_args()

    payload = asyncio.run(
        _run(
            domain=args.domain,
            region=args.region,
            max_scroll_pages=args.max_scroll_pages,
            timeout=args.timeout,
            proxy=args.proxy,
        )
    )
    if args.pretty:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
