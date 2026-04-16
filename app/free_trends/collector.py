from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse

from playwright.async_api import BrowserContext, Page, Response, async_playwright


class TrendsBlockedError(Exception):
    pass


class TrendsCollectionError(Exception):
    pass


@dataclass(slots=True)
class RisingQuery:
    query: str
    value_label: str


@dataclass(slots=True)
class BatchCapture:
    rising_by_term: dict[str, list[RisingQuery]] = field(default_factory=dict)


class FreeTrendsCollector:
    BASE_URL = "https://trends.google.com/trends/explore"

    def __init__(
        self,
        *,
        headless: bool,
        browser_channel: str | None,
        browser_executable_path: str | None,
        browser_user_data_dir: str,
        language: str,
        timeout_ms: int,
    ):
        self.headless = headless
        self.browser_channel = browser_channel
        self.browser_executable_path = browser_executable_path
        self.browser_user_data_dir = browser_user_data_dir
        self.language = language
        self.timeout_ms = timeout_ms
        self._playwright = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._capture = BatchCapture()
        self._blocked_message: str | None = None

    async def start(self) -> None:
        self._playwright = await async_playwright().start()
        launch_kwargs: dict[str, Any] = {
            "headless": self.headless,
            "locale": self.language,
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
            ),
            "viewport": {"width": 1440, "height": 900},
        }
        if self.browser_executable_path:
            launch_kwargs["executable_path"] = self.browser_executable_path
        elif self.browser_channel:
            launch_kwargs["channel"] = self.browser_channel
        self._context = await self._playwright.chromium.launch_persistent_context(
            str(Path(self.browser_user_data_dir).expanduser()),
            **launch_kwargs,
        )
        self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()
        self._page.set_default_timeout(self.timeout_ms)
        self._page.on("response", lambda response: asyncio.create_task(self._on_response(response)))

    async def close(self) -> None:
        if self._context is not None:
            await self._context.close()
        if self._playwright is not None:
            await self._playwright.stop()

    async def collect_batch(
        self,
        *,
        keywords: list[str],
        time_range: str,
        geo: str,
    ) -> BatchCapture:
        if self._page is None:
            raise TrendsCollectionError("Collector has not been started.")

        self._capture = BatchCapture(rising_by_term={term: [] for term in keywords})
        self._blocked_message = None
        url = self._build_compare_url(keywords=keywords, time_range=time_range, geo=geo)
        response = await self._page.goto(url, wait_until="domcontentloaded")
        await self._raise_if_blocked_landing(response)
        await self._dismiss_cookie_banner()
        await self._ensure_classic_explore()
        await self._dismiss_cookie_banner()
        await self._wait_for_related_queries(expected_terms=keywords)
        return self._capture

    async def _wait_for_related_queries(self, expected_terms: list[str]) -> None:
        deadline = asyncio.get_running_loop().time() + (self.timeout_ms / 1000)
        while asyncio.get_running_loop().time() < deadline:
            if self._blocked_message:
                raise TrendsBlockedError(self._blocked_message)
            populated = [
                term for term in expected_terms if self._capture.rising_by_term.get(term)
            ]
            if populated:
                return
            await self._raise_if_blocked_page()
            await asyncio.sleep(0.25)
        await self._capture_dom_fallback(expected_terms)
        populated = [term for term in expected_terms if self._capture.rising_by_term.get(term)]
        if populated:
            return
        raise TrendsCollectionError("Timed out waiting for Google Trends related queries.")

    async def _on_response(self, response: Response) -> None:
        url = response.url
        if response.status in {403, 429} and "trends.google.com/trends" in url:
            self._blocked_message = f"Google Trends returned HTTP {response.status}."
            return
        if "/trends/api/widgetdata/relatedsearches" not in url:
            return

        try:
            payload = self._parse_google_json(await response.text())
        except Exception:
            return
        keyword = self._extract_related_keyword_from_url(url)
        if not keyword:
            return
        self._capture.rising_by_term[keyword] = self._extract_rising_queries(payload)

    async def _raise_if_blocked_landing(self, response: Response | None) -> None:
        if response is not None and response.status in {403, 429}:
            raise TrendsBlockedError(f"Google Trends returned HTTP {response.status}.")
        await self._raise_if_blocked_page()

    async def _raise_if_blocked_page(self) -> None:
        if self._page is None:
            return
        try:
            title = (await self._page.title()).lower()
            body = (await self._page.locator("body").inner_text()).lower()
        except Exception:
            return
        markers = ("too many requests", "unusual traffic", "captcha", "not a robot")
        if any(marker in title or marker in body for marker in markers):
            raise TrendsBlockedError("Google Trends returned a blocked, captcha, or rate-limited page.")

    async def _dismiss_cookie_banner(self) -> None:
        if self._page is None:
            return
        selectors = (
            "text=Got it",
            "button:has-text('Got it')",
            "button:has-text('I agree')",
            "button:has-text('Accept all')",
            "button:has-text('全部接受')",
            "button:has-text('我同意')",
        )
        for selector in selectors:
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
        hint = "Back to Classic Explore"
        try:
            title = await self._page.title()
            body = await self._page.locator("body").inner_text()
        except Exception:
            return
        if hint not in title and hint not in body:
            return
        selectors = (
            "text=Back to Classic Explore",
            "a:has-text('Back to Classic Explore')",
            "button:has-text('Back to Classic Explore')",
        )
        for selector in selectors:
            try:
                locator = self._page.locator(selector).first
                if await locator.is_visible():
                    await locator.click(timeout=2000)
                    await self._page.wait_for_load_state("domcontentloaded", timeout=10000)
                    await self._page.wait_for_timeout(1200)
                    return
            except Exception:
                continue
        raise TrendsCollectionError("Detected the new Explore UI and could not switch back to Classic Explore.")

    async def _capture_dom_fallback(self, expected_terms: list[str]) -> None:
        if self._page is None:
            return
        await self._scroll_for_dom_sections()
        body_text = await self._page.locator("body").inner_text()
        parsed = self._parse_dom_related_queries(body_text, expected_terms)
        for keyword, rising in parsed.items():
            if rising:
                self._capture.rising_by_term[keyword] = rising

    async def _scroll_for_dom_sections(self) -> None:
        if self._page is None:
            return
        try:
            for _ in range(6):
                await self._page.mouse.wheel(0, 2200)
                await self._page.wait_for_timeout(700)
        except Exception:
            return

    @staticmethod
    def _build_compare_url(*, keywords: list[str], time_range: str, geo: str) -> str:
        query = ",".join(keywords)
        geo_param = f"&geo={quote(geo)}" if geo else ""
        return f"{FreeTrendsCollector.BASE_URL}?date={quote(time_range)}&q={quote(query)}{geo_param}&hl=en-US"

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

    @staticmethod
    def _extract_rising_queries(payload: dict) -> list[RisingQuery]:
        ranked_lists = payload.get("default", {}).get("rankedList") or payload.get("rankedList") or []
        target_list = None
        if len(ranked_lists) > 1 and ranked_lists[1].get("rankedKeyword"):
            target_list = ranked_lists[1]
        elif ranked_lists:
            first = ranked_lists[0]
            keywords_type = str(first.get("keywordsType") or first.get("type") or "").lower()
            if "rising" in keywords_type:
                target_list = first
        if not target_list:
            return []

        rising: list[RisingQuery] = []
        for entry in target_list.get("rankedKeyword") or []:
            query = str(entry.get("query") or "").strip()
            value = entry.get("value")
            if not query:
                continue
            if isinstance(value, (int, float)):
                value_label = f"{int(value)}%"
            else:
                value_label = str(value or "").strip() or "Breakout"
            rising.append(RisingQuery(query=query, value_label=value_label))
        return rising

    @staticmethod
    def _parse_dom_related_queries(body_text: str, compare_keywords: list[str]) -> dict[str, list[RisingQuery]]:
        lines = [line.strip() for line in body_text.splitlines() if line.strip()]
        compare_map = {keyword.casefold(): keyword for keyword in compare_keywords}
        compare_set = set(compare_map.keys())
        results: dict[str, list[RisingQuery]] = {keyword: [] for keyword in compare_keywords}
        current_keyword: str | None = compare_keywords[0] if len(compare_keywords) == 1 else None
        collecting = False
        pending_query: str | None = None

        def flush_pending(value_label: str | None = None) -> None:
            nonlocal pending_query
            if current_keyword and pending_query and value_label:
                results.setdefault(current_keyword, []).append(
                    RisingQuery(query=pending_query, value_label=value_label)
                )
            pending_query = None

        for line in lines:
            lowered = line.casefold()
            if lowered in compare_set:
                flush_pending()
                current_keyword = compare_map[lowered]
                collecting = False
                continue

            if lowered in {"related queries", "相关查询"}:
                collecting = True
                if current_keyword is None and compare_keywords:
                    current_keyword = compare_keywords[0]
                continue

            if not collecting:
                continue

            if FreeTrendsCollector._is_related_queries_boundary(line):
                flush_pending()
                if line.startswith(("Showing ", "当前显示的是第")):
                    collecting = False
                continue

            if re.fullmatch(r"\d+", line):
                flush_pending()
                pending_query = None
                continue

            if pending_query is None:
                if FreeTrendsCollector._is_control_line(line):
                    continue
                pending_query = line
                continue

            if FreeTrendsCollector._looks_like_value_label(line):
                flush_pending(line)
                continue

        flush_pending()
        return results

    @staticmethod
    def _looks_like_value_label(line: str) -> bool:
        lowered = line.casefold()
        if lowered in {"breakout", "飙升", "爆发式增长"}:
            return True
        return bool(re.fullmatch(r"\+?\d[\d,]*%", line))

    @staticmethod
    def _is_control_line(line: str) -> bool:
        lowered = line.casefold()
        control_lines = {
            "analyze",
            "分析",
            "rising",
            "top",
            "搜索量上升",
            "热门",
            "file_download",
            "code",
            "share",
            "help_outline",
            "more_vert",
        }
        return lowered in control_lines

    @staticmethod
    def _is_related_queries_boundary(line: str) -> bool:
        lowered = line.casefold()
        if lowered.startswith("showing ") or line.startswith("当前显示的是第"):
            return True
        boundaries = {
            "interest by region",
            "region",
            "地区热度",
            "区域热度",
            "compared breakdown by region",
            "related topics",
            "相关主题",
        }
        return lowered in boundaries or FreeTrendsCollector._is_control_line(line) and lowered != "搜索量上升"
