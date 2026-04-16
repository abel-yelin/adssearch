import argparse
import asyncio
import json
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


from app.collectors.sitedata_traffic_collector import SiteDataTrafficCollectorError
from app.core.config import get_settings
from app.schemas.sitedata import SiteDataTrafficRequest
from app.services.sitedata_service import SiteDataTrafficService


async def _run(args: argparse.Namespace) -> int:
    request = SiteDataTrafficRequest(
        domain=args.domain,
        collection_mode="direct",
        sync_cf_token_from_browser=args.sync_cf_token_from_browser,
        client_id=args.client_id,
        cf_token=args.cf_token,
        proxy=args.proxy,
        timeout_seconds=args.timeout_seconds,
        browser_mode=args.browser_mode,
        browser_cdp_url=args.browser_cdp_url,
        browser_executable_path=args.browser_executable_path,
        browser_user_data_dir=args.browser_user_data_dir,
        browser_channel=args.browser_channel,
        browser_extension_path=args.browser_extension_path,
        browser_headless=not args.show_browser,
        browser_timeout_ms=args.browser_timeout_ms,
        browser_pre_click_wait_ms=args.browser_pre_click_wait_ms,
        browser_post_click_wait_ms=args.browser_post_click_wait_ms,
    )

    try:
        response = await SiteDataTrafficService().fetch_traffic(request)
    except SiteDataTrafficCollectorError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "code": exc.code,
                    "message": exc.message,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2

    summary = response.model_dump()
    summary["ok"] = True
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Smoke test the SiteData traffic collector.")
    parser.add_argument("--domain", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=30)
    parser.add_argument("--proxy", default=None)
    parser.add_argument("--sync-cf-token-from-browser", action="store_true")
    parser.add_argument("--client-id", default=None)
    parser.add_argument("--cf-token", default=None)
    parser.add_argument("--browser-mode", choices=["isolated", "cdp", "persistent"], default=settings.trend_browser_mode)
    parser.add_argument("--browser-cdp-url", default=settings.trend_browser_cdp_url)
    parser.add_argument("--browser-executable-path", default=settings.trend_browser_executable_path)
    parser.add_argument("--browser-user-data-dir", default=settings.trend_browser_user_data_dir)
    parser.add_argument("--browser-channel", default=settings.trend_browser_channel)
    parser.add_argument("--browser-extension-path", default=settings.trend_browser_extension_path)
    parser.add_argument("--browser-timeout-ms", type=int, default=30000)
    parser.add_argument("--browser-pre-click-wait-ms", type=int, default=3000)
    parser.add_argument("--browser-post-click-wait-ms", type=int, default=8000)
    parser.add_argument("--show-browser", action="store_true")
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
