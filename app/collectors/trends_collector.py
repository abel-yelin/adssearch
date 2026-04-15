import asyncio
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict
from urllib.parse import urljoin
from urllib.parse import quote, unquote, urlparse, parse_qs

import httpx
from playwright.async_api import Browser, BrowserContext, Page, Response, async_playwright


class CaptureBatchResult(TypedDict):
    related_queries: list[dict]
    multiline_data: dict | None
    raw_requests: list[dict]


class TrendsCollectorError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class _CaptureState:
    related_queries: list[dict]
    multiline_data: dict | None
    raw_requests: list[dict]
    blocked_error: TrendsCollectorError | None


class GoogleTrendsCollector:
    BASE_URL = "https://trends.google.com/trends/explore"
    CLASSIC_EXPLORE_HINT = "Back to Classic Explore"
    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    )

    def __init__(
        self,
        headless: bool = True,
        proxy: str | None = None,
        language: str = "en-US",
        timeout_ms: int = 45000,
        browser_mode: str = "isolated",
        browser_cdp_url: str | None = None,
        browser_executable_path: str | None = None,
        browser_user_data_dir: str | None = None,
        browser_channel: str | None = "chrome",
        browser_extension_path: str | None = None,
    ):
        self.headless = headless
        self.proxy = proxy
        self.language = language
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
        self._owns_context = False
        self._owns_page = False
        self._cdp_session = None
        self._capture_state = _CaptureState(
            related_queries=[],
            multiline_data=None,
            raw_requests=[],
            blocked_error=None,
        )

    async def start(self) -> None:
        self._playwright = await async_playwright().start()
        if self.browser_mode == "cdp":
            if not self.browser_cdp_url:
                raise TrendsCollectorError("invalid_browser_config", "CDP mode requires browser_cdp_url.")
            cdp_endpoint = await self._resolve_cdp_endpoint(self.browser_cdp_url)
            self._browser = await self._playwright.chromium.connect_over_cdp(cdp_endpoint)
            existing_context = self._browser.contexts[0] if self._browser.contexts else None
            self._context = existing_context or await self._browser.new_context()
            self._owns_context = existing_context is None
            existing_page = self._pick_existing_trends_page(self._context)
            self._page = existing_page or await self._context.new_page()
            self._owns_page = existing_page is None
            await self._configure_page_runtime()
            return

        if self.browser_mode == "persistent":
            if not self.browser_user_data_dir:
                raise TrendsCollectorError("invalid_browser_config", "Persistent mode requires browser_user_data_dir.")
            launch_kwargs = {
                "headless": self.headless,
                "locale": self.language,
                "timezone_id": "UTC",
                "user_agent": self.DEFAULT_USER_AGENT,
                "viewport": {"width": 1440, "height": 900},
                "screen": {"width": 1440, "height": 900},
            }
            if self.proxy:
                launch_kwargs["proxy"] = {"server": self.proxy}
            if self.browser_executable_path:
                launch_kwargs["executable_path"] = self.browser_executable_path
            elif self.browser_channel:
                launch_kwargs["channel"] = self.browser_channel
            if self.browser_extension_path:
                extension_path = str(Path(self.browser_extension_path).expanduser())
                launch_kwargs["args"] = [
                    f"--disable-extensions-except={extension_path}",
                    f"--load-extension={extension_path}",
                ]
            self._context = await self._playwright.chromium.launch_persistent_context(
                str(Path(self.browser_user_data_dir).expanduser()),
                **launch_kwargs,
            )
            self._owns_context = True
            existing_page = self._context.pages[0] if self._context.pages else None
            self._page = existing_page or await self._context.new_page()
            self._owns_page = existing_page is None
            await self._configure_page_runtime()
            return

        launch_kwargs = {"headless": self.headless}
        if self.proxy:
            launch_kwargs["proxy"] = {"server": self.proxy}
        self._browser = await self._playwright.chromium.launch(**launch_kwargs)
        self._context = await self._browser.new_context(
            locale=self.language,
            timezone_id="UTC",
            user_agent=self.DEFAULT_USER_AGENT,
            viewport={"width": 1440, "height": 900},
            screen={"width": 1440, "height": 900},
        )
        self._owns_context = True
        self._page = await self._context.new_page()
        self._owns_page = True
        await self._configure_page_runtime()

    async def close(self) -> None:
        if self._owns_page and self._page is not None:
            await self._page.close()
        if self._owns_context and self._context is not None:
            await self._context.close()
        if self._browser is not None:
            await self._browser.close()
        if self._playwright is not None:
            await self._playwright.stop()

    async def capture(
        self,
        base_keyword: str,
        keywords: list[str],
        time_range: str,
        geo: str = "",
        timezone_offset: int = 0,
    ) -> CaptureBatchResult:
        if not keywords:
            raise TrendsCollectorError("empty_batch", "No candidate keywords were provided.")
        if self._page is None:
            raise TrendsCollectorError("collector_not_started", "Collector has not been started.")

        self._capture_state = _CaptureState(
            related_queries=[],
            multiline_data=None,
            raw_requests=[],
            blocked_error=None,
        )
        compare_keywords = [base_keyword, *keywords]
        url = self._build_explore_url(compare_keywords, time_range, geo=geo, timezone_offset=timezone_offset)

        existing_dom = await self._capture_existing_dom_if_ready(url, compare_keywords)
        if existing_dom is not None:
            return existing_dom

        try:
            response = await self._page.goto(url, wait_until="domcontentloaded")
            await self._raise_if_blocked_landing(response)
            await self._prepare_explore_page()
            await self._refresh_if_stuck_loading()
            await self._wait_for_capture(expected_related=max(len(keywords), 1))
        except TrendsCollectorError:
            raise
        except asyncio.TimeoutError as exc:
            await self._raise_if_blocked_page()
            recovered = await self._recover_with_auto_reload(
                compare_keywords=compare_keywords,
                expected_related=max(len(keywords), 1),
            )
            if recovered is not None:
                return recovered
            dom_fallback = await self._capture_dom_fallback(compare_keywords)
            if dom_fallback["multiline_data"] is not None:
                return dom_fallback
            raise TrendsCollectorError("network_timeout", "Timed out waiting for Google Trends widgets.") from exc
        except Exception as exc:
            raise TrendsCollectorError("playwright_navigation_error", str(exc)) from exc

        if self._capture_state.multiline_data is None:
            raise TrendsCollectorError("empty_response", "Multiline response was not captured.")

        return {
            "related_queries": self._capture_state.related_queries,
            "multiline_data": self._capture_state.multiline_data,
            "raw_requests": self._capture_state.raw_requests,
        }

    @staticmethod
    def _pick_existing_trends_page(context: BrowserContext) -> Page | None:
        for page in context.pages:
            if page.url.startswith("https://trends.google.com/trends/explore"):
                return page
        return None

    async def _capture_existing_dom_if_ready(
        self,
        target_url: str,
        compare_keywords: list[str],
    ) -> CaptureBatchResult | None:
        if self._page is None:
            return None
        current_url = self._page.url or ""
        if not current_url.startswith("https://trends.google.com/trends/explore"):
            return None
        if current_url != target_url:
            return None

        dom_fallback = await self._capture_dom_fallback(compare_keywords)
        if dom_fallback["multiline_data"] is None:
            return None
        return dom_fallback

    async def _configure_page_runtime(self) -> None:
        if self._context is None or self._page is None:
            raise TrendsCollectorError("collector_not_started", "Collector has not been started.")

        try:
            await self._context.set_extra_http_headers(
                {
                    "Accept-Language": f"{self.language},en;q=0.9",
                    "Upgrade-Insecure-Requests": "1",
                }
            )
            await self._context.add_init_script(
                """
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4] });
                """
            )
        except Exception:
            pass

        try:
            self._cdp_session = await self._context.new_cdp_session(self._page)
        except Exception:
            self._cdp_session = None

        self._page.set_default_timeout(self.timeout_ms)
        self._page.on("response", lambda response: asyncio.create_task(self._on_response(response)))


    async def _resolve_cdp_endpoint(self, cdp_url: str) -> str:
        parsed = urlparse(cdp_url)
        if parsed.scheme in {"ws", "wss"}:
            return cdp_url

        version_url = urljoin(cdp_url.rstrip("/") + "/", "json/version")
        try:
            async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
                response = await client.get(version_url)
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            raise TrendsCollectorError(
                "browser_connect_error",
                f"Failed to resolve Chrome DevTools endpoint from '{version_url}': {exc}",
            ) from exc

        websocket_url = payload.get("webSocketDebuggerUrl")
        if not websocket_url:
            raise TrendsCollectorError(
                "browser_connect_error",
                f"Chrome DevTools response from '{version_url}' did not include webSocketDebuggerUrl.",
            )
        return websocket_url

    async def _wait_for_capture(self, expected_related: int) -> None:
        deadline = asyncio.get_running_loop().time() + (self.timeout_ms / 1000)
        while asyncio.get_running_loop().time() < deadline:
            if self._capture_state.blocked_error is not None:
                raise self._capture_state.blocked_error
            if self._capture_state.multiline_data and len(self._capture_state.related_queries) >= expected_related:
                return
            await asyncio.sleep(0.25)
        raise asyncio.TimeoutError

    async def _recover_with_auto_reload(
        self,
        compare_keywords: list[str],
        expected_related: int,
    ) -> CaptureBatchResult | None:
        if self._page is None:
            return None

        for _ in range(3):
            await self._hard_refresh_current_page()
            await self._prepare_explore_page()

            try:
                await self._wait_for_capture_after_reload(expected_related)
            except TrendsCollectorError:
                raise
            except asyncio.TimeoutError:
                pass

            if self._capture_state.multiline_data is not None:
                return {
                    "related_queries": self._capture_state.related_queries,
                    "multiline_data": self._capture_state.multiline_data,
                    "raw_requests": self._capture_state.raw_requests,
                }

            dom_fallback = await self._capture_dom_fallback(compare_keywords)
            if dom_fallback["multiline_data"] is not None:
                return dom_fallback

        return None

    async def _wait_for_capture_after_reload(self, expected_related: int) -> None:
        deadline = asyncio.get_running_loop().time() + min(15, self.timeout_ms / 1000)
        while asyncio.get_running_loop().time() < deadline:
            if self._capture_state.blocked_error is not None:
                raise self._capture_state.blocked_error
            if self._capture_state.multiline_data and len(self._capture_state.related_queries) >= expected_related:
                return
            if self._capture_state.multiline_data is not None:
                return
            if not await self._is_loading_shell_only():
                return
            await asyncio.sleep(0.5)
        raise asyncio.TimeoutError

    async def _refresh_if_stuck_loading(self) -> None:
        if self._page is None:
            return

        for _ in range(2):
            await asyncio.sleep(3)
            if self._capture_state.raw_requests or self._capture_state.multiline_data or self._capture_state.related_queries:
                return
            if not await self._is_loading_shell_only():
                return

            await self._hard_refresh_current_page()
            await self._dismiss_cookie_banner()
            await self._prepare_explore_page()

    async def _is_loading_shell_only(self) -> bool:
        if self._page is None:
            return False

        body_text = ""
        try:
            body_text = await self._page.locator("body").inner_text()
        except Exception:
            return False

        shell_markers = (
            "Worldwide, Past 12 months",
            "United States, Past 24 hours",
            "Search term",
            "Interest over time",
        )
        if not any(marker in body_text for marker in shell_markers):
            return False

        data_markers = (
            "Related queries",
            "Compared breakdown by region",
            "Interest by region",
            "\t",
            "Showing 1-5 of",
        )
        return not any(marker in body_text for marker in data_markers)

    async def _hard_refresh_current_page(self) -> None:
        if self._page is None:
            return

        try:
            await self._page.bring_to_front()
        except Exception:
            pass

        if self._cdp_session is not None:
            try:
                await self._cdp_session.send("Network.enable")
                await self._cdp_session.send("Network.clearBrowserCache")
                await self._cdp_session.send("Page.reload", {"ignoreCache": True})
                await self._page.wait_for_load_state("domcontentloaded", timeout=self.timeout_ms)
                await self._page.wait_for_timeout(2500)
                if not await self._is_loading_shell_only():
                    return
            except Exception:
                pass

        if await self._browser_style_refresh():
            return

        current_url = self._page.url
        response = await self._page.goto(current_url, wait_until="domcontentloaded")
        await self._raise_if_blocked_landing(response)

    async def _browser_style_refresh(self) -> bool:
        if self._page is None:
            return False

        for shortcut in ("F5", "Control+R"):
            try:
                await self._page.bring_to_front()
            except Exception:
                pass
            try:
                await self._page.keyboard.press(shortcut)
                await self._page.wait_for_load_state("domcontentloaded", timeout=self.timeout_ms)
                await self._page.wait_for_timeout(2500)
                return True
            except Exception:
                continue
        return False

    async def _capture_dom_fallback(self, compare_keywords: list[str]) -> CaptureBatchResult:
        if self._page is None:
            return {
                "related_queries": [],
                "multiline_data": None,
                "raw_requests": [],
            }

        await self._scroll_for_dom_sections()
        body_text = await self._page.locator("body").inner_text()
        multiline_data = self._parse_dom_multiline_data(body_text)
        related_queries = self._parse_dom_related_queries(body_text, compare_keywords)

        raw_requests = []
        if multiline_data is not None or related_queries:
            raw_requests.append(
                {
                    "url": "dom://google-trends-page",
                    "status": 200,
                    "payload": {
                        "source": "dom_fallback",
                        "multiline_data_present": multiline_data is not None,
                        "related_queries_count": len(related_queries),
                    },
                }
            )

        return {
            "related_queries": related_queries,
            "multiline_data": multiline_data,
            "raw_requests": raw_requests,
        }

    async def _scroll_for_dom_sections(self) -> None:
        if self._page is None:
            return
        try:
            for _ in range(3):
                await self._page.mouse.wheel(0, 2500)
                await self._page.wait_for_timeout(800)
        except Exception:
            return

    @staticmethod
    def _parse_dom_multiline_data(body_text: str) -> dict | None:
        lines = [line.strip() for line in body_text.splitlines() if line.strip()]
        timeline_rows = []
        for line in lines:
            if "\t" not in line:
                continue
            parts = [part.strip() for part in line.split("\t") if part.strip()]
            if len(parts) < 3:
                continue
            if not re.search(r"\d", parts[0]):
                continue
            values = []
            for raw in parts[1:]:
                try:
                    values.append(int(raw.replace(",", "")))
                except ValueError:
                    values = []
                    break
            if values:
                timeline_rows.append(
                    {
                        "formattedTime": parts[0],
                        "value": values,
                    }
                )

        if len(timeline_rows) < 10:
            return None

        return {
            "default": {
                "timelineData": timeline_rows,
            }
        }

    @staticmethod
    def _parse_dom_related_queries(body_text: str, compare_keywords: list[str]) -> list[dict]:
        lines = [line.strip() for line in body_text.splitlines() if line.strip()]
        compare_set = {keyword.lower() for keyword in compare_keywords}
        related_queries: list[dict] = []
        current_keyword = None
        collecting = False
        ranked_keywords: list[dict] = []
        current_entry: str | None = None

        def flush_current() -> None:
            nonlocal ranked_keywords, collecting, current_entry, current_keyword
            if current_keyword and ranked_keywords:
                related_queries.append(
                    {
                        "keyword": current_keyword,
                        "payload": {
                            "default": {
                                "rankedList": [
                                    {"rankedKeyword": []},
                                    {"rankedKeyword": ranked_keywords.copy()},
                                ]
                            }
                        },
                    }
                )
            ranked_keywords = []
            collecting = False
            current_entry = None

        for line in lines:
            lowered = line.lower()
            if lowered in compare_set:
                flush_current()
                current_keyword = line
                continue
            if line == "Related queries" and current_keyword:
                collecting = True
                continue
            if not collecting:
                continue
            if line.startswith("Showing "):
                flush_current()
                continue
            if line in {"Analyze", "Rising", "Top", "Region", "Interest by region", "file_download", "code", "share", "help_outline"}:
                continue
            if re.fullmatch(r"\d+", line):
                current_entry = None
                continue
            if line == "more_vert":
                if current_entry:
                    ranked_keywords.append({"query": current_entry})
                    current_entry = None
                continue
            if current_entry is None:
                current_entry = line

        flush_current()
        return related_queries

    async def _on_response(self, response: Response) -> None:
        url = response.url
        if response.status in {403, 429} and "trends.google.com/trends" in url:
            self._capture_state.blocked_error = TrendsCollectorError(
                "captcha_or_blocked",
                f"Google Trends returned HTTP {response.status}.",
            )
            return
        if "/trends/api/widgetdata/" not in url:
            return
        if "captcha" in url.lower():
            self._capture_state.blocked_error = TrendsCollectorError(
                "captcha_or_blocked",
                "Google Trends returned a blocked or captcha page.",
            )
            return

        try:
            raw_text = await response.text()
            payload = self._parse_google_json(raw_text)
        except json.JSONDecodeError:
            return
        except Exception:
            return

        self._capture_state.raw_requests.append(
            {
                "url": url,
                "status": response.status,
                "payload": payload,
            }
        )
        if "relatedsearches" in url:
            self._capture_state.related_queries.append(
                {
                    "keyword": self._extract_related_keyword_from_url(url),
                    "payload": payload,
                }
            )
        elif "multiline" in url:
            self._capture_state.multiline_data = payload

    async def _raise_if_blocked_landing(self, response: Response | None) -> None:
        if response is not None and response.status in {403, 429}:
            raise TrendsCollectorError("captcha_or_blocked", f"Google Trends returned HTTP {response.status}.")
        await self._raise_if_blocked_page()

    async def _raise_if_blocked_page(self) -> None:
        if self._page is None:
            return

        try:
            title = (await self._page.title()).lower()
            body = (await self._page.locator("body").inner_text()).lower()
        except Exception:
            return

        blocked_markers = (
            "too many requests",
            "unusual traffic",
            "detected unusual traffic",
            "not a robot",
            "captcha",
        )
        if any(marker in title or marker in body for marker in blocked_markers):
            raise TrendsCollectorError(
                "captcha_or_blocked",
                "Google Trends returned a blocked, captcha, or rate-limited page.",
            )

    async def _prepare_explore_page(self) -> None:
        if self._page is None:
            return

        await self._dismiss_cookie_banner()
        await self._ensure_classic_explore()
        await self._dismiss_cookie_banner()

    async def _dismiss_cookie_banner(self) -> None:
        if self._page is None:
            return

        cookie_selectors = (
            "text=Got it",
            "button:has-text('Got it')",
            "button:has-text('I agree')",
            "button:has-text('Accept all')",
        )
        for selector in cookie_selectors:
            try:
                locator = self._page.locator(selector).first
                if await locator.is_visible():
                    await locator.click(timeout=2000)
                    await self._page.wait_for_timeout(800)
                    return
            except Exception:
                continue

    async def _ensure_classic_explore(self) -> None:
        if self._page is None:
            return

        title = ""
        body = ""
        try:
            title = await self._page.title()
            body = await self._page.locator("body").inner_text()
        except Exception:
            return

        if self.CLASSIC_EXPLORE_HINT not in title and self.CLASSIC_EXPLORE_HINT not in body:
            return

        classic_selectors = (
            "text=Back to Classic Explore",
            "a:has-text('Back to Classic Explore')",
            "button:has-text('Back to Classic Explore')",
        )
        for selector in classic_selectors:
            try:
                locator = self._page.locator(selector).first
                if await locator.is_visible():
                    await locator.click(timeout=2000)
                    await self._page.wait_for_load_state("domcontentloaded", timeout=10000)
                    await self._page.wait_for_timeout(1200)
                    return
            except Exception:
                continue
        raise TrendsCollectorError(
            "new_explore_detected",
            "Google Trends opened the new Explore UI and could not be switched back to Classic Explore automatically.",
        )

    @staticmethod
    def _build_explore_url(
        keywords: list[str],
        time_range: str,
        geo: str = "",
        timezone_offset: int = 0,
    ) -> str:
        query = ",".join(keywords)
        geo_param = f"&geo={quote(geo)}" if geo else ""
        return (
            f"{GoogleTrendsCollector.BASE_URL}?date={quote(time_range)}&q={quote(query)}"
            f"{geo_param}&hl=en-US&tz={timezone_offset}"
        )

    @staticmethod
    def _parse_google_json(text: str) -> dict:
        cleaned = text.strip()
        if cleaned.startswith(")]}',"):
            cleaned = cleaned[5:]
        return json.loads(cleaned)

    @staticmethod
    def _extract_related_keyword_from_url(url: str) -> str:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        req_values = params.get("req") or []
        if not req_values:
            return ""
        try:
            req_payload = json.loads(unquote(req_values[0]))
        except Exception:
            return ""

        stack = [req_payload]
        while stack:
            current = stack.pop()
            if isinstance(current, dict):
                keyword = current.get("keyword")
                if isinstance(keyword, str):
                    return keyword
                stack.extend(current.values())
            elif isinstance(current, list):
                stack.extend(current)
        return ""
