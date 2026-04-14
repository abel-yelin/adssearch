import asyncio
import json
from dataclasses import dataclass
from typing import TypedDict
from urllib.parse import quote, unquote, urlparse, parse_qs

from playwright.async_api import BrowserContext, Page, Response, async_playwright


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
    ):
        self.headless = headless
        self.proxy = proxy
        self.language = language
        self.timeout_ms = timeout_ms
        self._playwright = None
        self._browser = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._capture_state = _CaptureState(
            related_queries=[],
            multiline_data=None,
            raw_requests=[],
            blocked_error=None,
        )

    async def start(self) -> None:
        self._playwright = await async_playwright().start()
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
        self._page = await self._context.new_page()
        self._page.set_default_timeout(self.timeout_ms)
        self._page.on("response", self._on_response)

    async def close(self) -> None:
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

        try:
            response = await self._page.goto(url, wait_until="domcontentloaded")
            await self._raise_if_blocked_landing(response)
            await self._wait_for_capture(expected_related=max(len(keywords), 1))
        except TrendsCollectorError:
            raise
        except asyncio.TimeoutError as exc:
            await self._raise_if_blocked_page()
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

    async def _wait_for_capture(self, expected_related: int) -> None:
        deadline = asyncio.get_running_loop().time() + (self.timeout_ms / 1000)
        while asyncio.get_running_loop().time() < deadline:
            if self._capture_state.blocked_error is not None:
                raise self._capture_state.blocked_error
            if self._capture_state.multiline_data and len(self._capture_state.related_queries) >= expected_related:
                return
            await asyncio.sleep(0.25)
        raise asyncio.TimeoutError

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
