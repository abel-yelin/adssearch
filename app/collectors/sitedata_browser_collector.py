import asyncio
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from app.collectors.sitedata_traffic_collector import SiteDataTrafficCollector, SiteDataTrafficCollectorError


class SiteDataBrowserCollector:
    def __init__(
        self,
        *,
        headless: bool = True,
        timeout_ms: int = 30000,
        browser_mode: str = "isolated",
        browser_cdp_url: str | None = None,
        browser_executable_path: str | None = None,
        browser_user_data_dir: str | None = None,
        browser_channel: str | None = "chrome",
        browser_extension_path: str | None = None,
    ):
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.browser_mode = browser_mode
        self.browser_cdp_url = browser_cdp_url
        self.browser_executable_path = browser_executable_path
        self.browser_user_data_dir = browser_user_data_dir
        self.browser_channel = browser_channel
        self.browser_extension_path = browser_extension_path
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._owns_browser = False
        self._owns_context = False
        self._requests: list[dict[str, Any]] = []
        self._console_logs: list[dict[str, str]] = []
        self._page_errors: list[str] = []

    async def start(self) -> None:
        self._playwright = await async_playwright().start()
        if self.browser_mode == "cdp":
            if not self.browser_cdp_url:
                raise SiteDataTrafficCollectorError("invalid_browser_config", "CDP mode requires browser_cdp_url.")
            cdp_endpoint = await self._resolve_cdp_endpoint(self.browser_cdp_url)
            self._browser = await self._playwright.chromium.connect_over_cdp(cdp_endpoint)
            existing_context = self._browser.contexts[0] if self._browser.contexts else None
            self._context = existing_context or await self._browser.new_context()
            self._owns_context = existing_context is None
        elif self.browser_mode == "persistent":
            if not self.browser_user_data_dir:
                raise SiteDataTrafficCollectorError(
                    "invalid_browser_config",
                    "Persistent mode requires browser_user_data_dir.",
                )
            launch_kwargs: dict[str, Any] = {
                "headless": self.headless,
                "viewport": {"width": 1440, "height": 900},
                "locale": "en-US",
            }
            if self.browser_executable_path:
                launch_kwargs["executable_path"] = self.browser_executable_path
            elif self.browser_channel:
                launch_kwargs["channel"] = self.browser_channel
            if self.browser_extension_path:
                extension_path = str(Path(self.browser_extension_path).expanduser())
                launch_kwargs["args"] = [
                    "--no-sandbox",
                    f"--disable-extensions-except={extension_path}",
                    f"--load-extension={extension_path}",
                ]
            self._context = await self._playwright.chromium.launch_persistent_context(
                str(Path(self.browser_user_data_dir).expanduser()),
                **launch_kwargs,
            )
            self._owns_context = True
        else:
            launch_kwargs: dict[str, Any] = {"headless": self.headless}
            if self.browser_executable_path:
                launch_kwargs["executable_path"] = self.browser_executable_path
            elif self.browser_channel:
                launch_kwargs["channel"] = self.browser_channel
            self._browser = await self._playwright.chromium.launch(**launch_kwargs)
            self._context = await self._browser.new_context(viewport={"width": 1440, "height": 900}, locale="en-US")
            self._owns_browser = True
            self._owns_context = True

        if self._context is None:
            raise SiteDataTrafficCollectorError("browser_connect_error", "Failed to initialize browser context.")

        existing_page = next((page for page in self._context.pages if "sitedata.dev" in page.url), None)
        self._page = existing_page or (self._context.pages[0] if self._context.pages else await self._context.new_page())
        self._page.set_default_timeout(self.timeout_ms)
        self._page.on("response", lambda response: asyncio.create_task(self._on_response(response)))
        self._page.on("console", lambda msg: self._console_logs.append({"type": msg.type, "text": msg.text}))
        self._page.on("pageerror", lambda exc: self._page_errors.append(str(exc)))

    async def close(self) -> None:
        if self._owns_context and self._context is not None:
            await self._context.close()
        if self._owns_browser and self._browser is not None:
            await self._browser.close()
        if self._playwright is not None:
            await self._playwright.stop()

    async def fetch(self, domain: str, *, pre_click_wait_ms: int = 3000, post_click_wait_ms: int = 8000) -> dict[str, Any]:
        if self._page is None:
            raise SiteDataTrafficCollectorError("collector_not_started", "Browser collector has not been started.")

        self._requests = []
        self._console_logs = []
        self._page_errors = []
        normalized_domain = SiteDataTrafficCollector._normalize_domain(domain)
        url = f"https://sitedata.dev/traffic/{normalized_domain}"

        await self._page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
        await self._page.wait_for_timeout(pre_click_wait_ms)

        storage_before = await self._read_storage()
        await self._page.get_by_role("button", name="Analyze").click(timeout=10000)
        await self._page.wait_for_timeout(post_click_wait_ms)
        storage_after = await self._read_storage()

        payload = self._extract_latest_payload()
        if payload is None:
            await self._raise_browser_failure(normalized_domain)

        payload["requested_domain"] = normalized_domain
        payload["resolved_domain"] = (payload.get("SiteName") or self._derive_resolved_domain()).lower()
        payload["browser_debug"] = {
            "storage_before": self._sanitize_storage_snapshot(storage_before),
            "storage_after": self._sanitize_storage_snapshot(storage_after),
            "request_count": len(self._requests),
            "console": [
                {"type": item["type"], "text": self._sanitize_console_text(item["text"])}
                for item in self._console_logs[:80]
            ],
            "page_errors": self._page_errors[:40],
        }
        return payload

    async def _read_storage(self) -> dict[str, Any]:
        if self._page is None:
            return {}
        return await self._page.evaluate(
            """() => ({
                href: location.href,
                localKeys: Object.keys(localStorage),
                userInfo: localStorage.getItem('userInfo'),
                anonClientId: localStorage.getItem('anonClientId'),
                cfToken: localStorage.getItem('cf_token')
            })"""
        )

    @staticmethod
    def _sanitize_storage_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
        user_info_raw = snapshot.get("userInfo")
        return {
            "href": snapshot.get("href"),
            "local_keys": snapshot.get("localKeys") or [],
            "has_user_info": bool(user_info_raw),
            "has_anon_client_id": bool(snapshot.get("anonClientId")),
            "has_cf_token": bool(snapshot.get("cfToken")),
        }

    @staticmethod
    def _sanitize_console_text(text: str) -> str:
        sanitized = text
        sanitized = re.sub(r"cf_token:\s*[^,}\]]+", "cf_token: [redacted]", sanitized)
        sanitized = re.sub(r"clientId:\s*[^,}\]]+", "clientId: [redacted]", sanitized)
        sanitized = re.sub(r"sign:\s*[^,}\]]+", "sign: [redacted]", sanitized)
        return sanitized

    def _extract_latest_payload(self) -> dict[str, Any] | None:
        successful_requests = [item for item in self._requests if item["status"] == 200 and isinstance(item["payload"], dict)]
        if not successful_requests:
            return None
        return successful_requests[-1]["payload"]

    async def _raise_browser_failure(self, domain: str) -> None:
        if any("Verification required before fetching traffic data" in item["text"] for item in self._console_logs):
            raise SiteDataTrafficCollectorError(
                "verification_required",
                f"SiteData requires a verified browser session before loading traffic for '{domain}'.",
            )
        raise SiteDataTrafficCollectorError(
            "browser_capture_failed",
            f"Browser session did not capture SiteData traffic data for '{domain}'.",
        )

    def _derive_resolved_domain(self) -> str:
        if self._page is None:
            return ""
        current_url = self._page.url.rstrip("/")
        return current_url.rsplit("/", 1)[-1]

    async def _on_response(self, response) -> None:
        if "traffic.sitedata.dev" not in response.url:
            return
        try:
            body = await response.text()
            payload = json.loads(body)
        except Exception:
            payload = None
            body = "<no-body>"
        self._requests.append(
            {
                "status": response.status,
                "url": response.url,
                "body": body[:1200],
                "payload": payload,
            }
        )

    @staticmethod
    async def _resolve_cdp_endpoint(cdp_url: str) -> str:
        if cdp_url.startswith(("ws://", "wss://")):
            return cdp_url

        version_url = urljoin(cdp_url.rstrip("/") + "/", "json/version")
        async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
            response = await client.get(version_url)
            response.raise_for_status()
            payload = response.json()

        websocket_url = payload.get("webSocketDebuggerUrl")
        if not websocket_url:
            raise SiteDataTrafficCollectorError(
                "browser_connect_error",
                f"Chrome DevTools response from '{version_url}' did not include webSocketDebuggerUrl.",
            )
        return websocket_url
