import argparse
import asyncio
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from app.core.config import get_settings
from app.schemas.sitedata import SiteDataTrafficRequest
from app.services.sitedata_service import SiteDataTrafficService


async def _run(args: argparse.Namespace) -> int:
    try:
        request = SiteDataTrafficRequest(
            domain=args.domain,
            collection_mode="browser",
            browser_mode=args.browser_mode,
            browser_cdp_url=args.browser_cdp_url,
            browser_executable_path=args.browser_executable_path,
            browser_user_data_dir=args.browser_user_data_dir,
            browser_channel=args.browser_channel,
            browser_extension_path=args.browser_extension_path,
            browser_headless=not args.show_browser,
            browser_timeout_ms=args.timeout_ms,
            browser_pre_click_wait_ms=args.pre_click_wait_ms,
            browser_post_click_wait_ms=args.post_click_wait_ms,
        )
        response = await SiteDataTrafficService().fetch_traffic(request)
        print(
            json.dumps(
                response.model_dump(),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except Exception as exc:
        code = getattr(exc, "code", "unexpected_error")
        message = getattr(exc, "message", str(exc))
        print(json.dumps({"ok": False, "code": code, "message": message}, ensure_ascii=False, indent=2))
        return 2


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Run a SiteData browser session smoke test.")
    parser.add_argument("--domain", required=True)
    parser.add_argument("--timeout-ms", type=int, default=30000)
    parser.add_argument("--pre-click-wait-ms", type=int, default=5000)
    parser.add_argument("--post-click-wait-ms", type=int, default=10000)
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
