import asyncio
from unittest.mock import patch

import pytest

from app.collectors.trends_collector import GoogleTrendsCollector, TrendsCollectorError, _CaptureState


class _FakeLocator:
    def __init__(self, text: str = "", visible: bool = False):
        self._text = text
        self._visible = visible
        self.clicked = False

    async def inner_text(self) -> str:
        return self._text

    async def is_visible(self, timeout: int | None = None) -> bool:
        return self._visible

    async def click(self, timeout: int | None = None) -> None:
        self.clicked = True

    @property
    def first(self):
        return self


class _FakePage:
    def __init__(self, response, title: str = "", body_text: str = "", locators: dict | None = None):
        self._response = response
        self._title = title
        self._body_text = body_text
        self._locators = locators or {}
        self.url = response.url
        self.load_state_calls = []
        self.wait_calls = []
        self.reload_calls = 0
        self.goto_calls = []
        self.front_calls = 0
        self.keyboard_presses = []
        self.url = response.url
        self.keyboard = self._Keyboard(self)

    class _Keyboard:
        def __init__(self, page):
            self._page = page

        async def press(self, shortcut: str):
            self._page.keyboard_presses.append(shortcut)

    async def goto(self, url: str, wait_until: str = "domcontentloaded"):
        self.goto_calls.append((url, wait_until))
        self.url = url
        return self._response

    async def reload(self, wait_until: str = "domcontentloaded"):
        self.reload_calls += 1
        return self._response

    async def title(self) -> str:
        return self._title

    def locator(self, selector: str):
        if selector == "body":
            return _FakeLocator(self._body_text, visible=True)
        return self._locators.get(selector, _FakeLocator())

    async def wait_for_load_state(self, state: str, timeout: int | None = None):
        self.load_state_calls.append((state, timeout))

    async def wait_for_timeout(self, timeout: int):
        self.wait_calls.append(timeout)

    async def bring_to_front(self):
        self.front_calls += 1


class _FakeResponse:
    def __init__(self, url: str, status: int, text: str = ""):
        self.url = url
        self.status = status
        self._text = text

    async def text(self) -> str:
        return self._text


class _FakePlaywrightFactory:
    def __call__(self):
        return self

    async def start(self):
        return self


class _SimplePage:
    def __init__(self, url: str):
        self.url = url


def test_capture_raises_blocked_when_landing_page_is_rate_limited():
    async def run():
        collector = GoogleTrendsCollector()
        collector._page = _FakePage(
            _FakeResponse(
                "https://trends.google.com/trends/explore?q=openai",
                429,
            ),
            title="Error 429 (Too Many Requests)!!1",
            body_text="We're sorry, but you have sent too many requests to us recently.",
        )

        with pytest.raises(TrendsCollectorError) as exc_info:
            await collector.capture(
                base_keyword="openai",
                keywords=["chatgpt"],
                time_range="today 12-m",
            )

        assert exc_info.value.code == "captcha_or_blocked"
        assert "HTTP 429" in exc_info.value.message

    asyncio.run(run())


def test_wait_for_capture_raises_blocked_error_immediately():
    async def run():
        collector = GoogleTrendsCollector(timeout_ms=100)
        collector._capture_state = _CaptureState(
            related_queries=[],
            multiline_data=None,
            raw_requests=[],
            blocked_error=TrendsCollectorError("captcha_or_blocked", "blocked"),
        )

        with pytest.raises(TrendsCollectorError) as exc_info:
            await collector._wait_for_capture(expected_related=1)

        assert exc_info.value.code == "captcha_or_blocked"

    asyncio.run(run())


def test_on_response_marks_rate_limit_as_blocked():
    async def run():
        collector = GoogleTrendsCollector()
        collector._capture_state = _CaptureState(
            related_queries=[],
            multiline_data=None,
            raw_requests=[],
            blocked_error=None,
        )

        await collector._on_response(
            _FakeResponse(
                "https://trends.google.com/trends/explore?q=openai",
                429,
            )
        )

        assert collector._capture_state.blocked_error is not None
        assert collector._capture_state.blocked_error.code == "captcha_or_blocked"

    asyncio.run(run())


def test_start_requires_cdp_url_in_cdp_mode():
    async def run():
        collector = GoogleTrendsCollector(browser_mode="cdp", browser_cdp_url=None)
        with patch("app.collectors.trends_collector.async_playwright", _FakePlaywrightFactory()):
            with pytest.raises(TrendsCollectorError) as exc_info:
                await collector.start()
        assert exc_info.value.code == "invalid_browser_config"

    asyncio.run(run())


def test_start_requires_user_data_dir_in_persistent_mode():
    async def run():
        collector = GoogleTrendsCollector(browser_mode="persistent", browser_user_data_dir=None)
        with patch("app.collectors.trends_collector.async_playwright", _FakePlaywrightFactory()):
            with pytest.raises(TrendsCollectorError) as exc_info:
                await collector.start()
        assert exc_info.value.code == "invalid_browser_config"

    asyncio.run(run())


def test_resolve_cdp_endpoint_returns_websocket_url_unchanged():
    async def run():
        collector = GoogleTrendsCollector(browser_mode="cdp", browser_cdp_url="ws://127.0.0.1:9222/devtools/browser/demo")
        resolved = await collector._resolve_cdp_endpoint("ws://127.0.0.1:9222/devtools/browser/demo")
        assert resolved == "ws://127.0.0.1:9222/devtools/browser/demo"

    asyncio.run(run())


def test_pick_existing_trends_page_prefers_open_explore_tab():
    class _FakeContext:
        def __init__(self):
            self.pages = [
                _SimplePage("devtools://devtools/bundled/devtools_app.html"),
                _SimplePage("https://trends.google.com/trends/explore?q=image"),
                _SimplePage("chrome://newtab/"),
            ]

    context = _FakeContext()
    page = GoogleTrendsCollector._pick_existing_trends_page(context)
    assert page is not None
    assert page.url.startswith("https://trends.google.com/trends/explore")




def test_prepare_explore_page_clicks_cookie_banner():
    async def run():
        cookie = _FakeLocator(visible=True)
        collector = GoogleTrendsCollector()
        collector._page = _FakePage(
            _FakeResponse("https://trends.google.com/trends/explore?q=image", 200),
            title="Explore - Google Trends",
            body_text="Explore",
            locators={"text=Got it": cookie},
        )

        await collector._prepare_explore_page()

        assert cookie.clicked is True

    asyncio.run(run())


def test_prepare_explore_page_switches_to_classic_when_new_ui_detected():
    async def run():
        switcher = _FakeLocator(visible=True)
        collector = GoogleTrendsCollector()
        collector._page = _FakePage(
            _FakeResponse("https://trends.google.com/trends/explore?q=image", 200),
            title="Explore - Google Trends",
            body_text="Back to Classic Explore",
            locators={"text=Back to Classic Explore": switcher},
        )

        await collector._prepare_explore_page()

        assert switcher.clicked is True
        assert collector._page.load_state_calls

    asyncio.run(run())


def test_prepare_explore_page_raises_when_new_ui_cannot_switch():
    async def run():
        collector = GoogleTrendsCollector()
        collector._page = _FakePage(
            _FakeResponse("https://trends.google.com/trends/explore?q=image", 200),
            title="Explore - Google Trends",
            body_text="Back to Classic Explore",
        )

        with pytest.raises(TrendsCollectorError) as exc_info:
            await collector._prepare_explore_page()

        assert exc_info.value.code == "new_explore_detected"

    asyncio.run(run())


def test_refresh_if_stuck_loading_reloads_when_page_has_no_requests():
    async def run():
        collector = GoogleTrendsCollector()
        collector._page = _FakePage(
            _FakeResponse("https://trends.google.com/trends/explore?q=image", 200),
            title="Explore - Google Trends",
            body_text="Worldwide, Past 12 months\nInterest over time\nSearch term",
        )
        collector._capture_state = _CaptureState(
            related_queries=[],
            multiline_data=None,
            raw_requests=[],
            blocked_error=None,
        )

        await collector._refresh_if_stuck_loading()

        assert collector._page.goto_calls or collector._page.keyboard_presses

    asyncio.run(run())


def test_refresh_if_stuck_loading_skips_reload_after_requests_arrive():
    async def run():
        collector = GoogleTrendsCollector()
        collector._page = _FakePage(
            _FakeResponse("https://trends.google.com/trends/explore?q=image", 200),
            title="Explore - Google Trends",
            body_text="Worldwide, Past 12 months\nInterest over time\nSearch term",
        )
        collector._capture_state = _CaptureState(
            related_queries=[],
            multiline_data={"default": {}},
            raw_requests=[{"url": "https://trends.google.com/trends/api/widgetdata/multiline", "status": 200, "payload": {}}],
            blocked_error=None,
        )

        await collector._refresh_if_stuck_loading()

        assert collector._page.reload_calls == 0

    asyncio.run(run())


def test_hard_refresh_uses_browser_style_refresh_when_shell_only_remains():
    async def run():
        collector = GoogleTrendsCollector()
        collector._page = _FakePage(
            _FakeResponse("https://trends.google.com/trends/explore?q=image", 200),
            title="Explore - Google Trends",
            body_text="Worldwide, Past 12 months\nInterest over time\nSearch term",
        )

        class _FakeCdp:
            async def send(self, method: str, params=None):
                return None

        collector._cdp_session = _FakeCdp()
        await collector._hard_refresh_current_page()

        assert collector._page.front_calls >= 1
        assert collector._page.keyboard_presses

    asyncio.run(run())


def test_capture_recovers_after_timeout_with_dom_fallback_reload():
    async def run():
        collector = GoogleTrendsCollector(timeout_ms=50)
        collector._page = _FakePage(
            _FakeResponse("https://trends.google.com/trends/explore?q=music", 200),
            title="Explore - Google Trends",
            body_text="Worldwide, Past 12 months\nInterest over time\nSearch term",
        )
        collector._capture_state = _CaptureState(
            related_queries=[],
            multiline_data=None,
            raw_requests=[],
            blocked_error=None,
        )

        recovered_payload = {
            "related_queries": [{"keyword": "music", "payload": {"default": {}}}],
            "multiline_data": {"default": {"timelineData": [{"formattedTime": "Apr 1", "value": [1]}]}},
            "raw_requests": [{"url": "dom://google-trends-page", "status": 200, "payload": {}}],
        }

        async def fake_wait(expected_related: int) -> None:
            raise asyncio.TimeoutError

        async def fake_dom(compare_keywords: list[str]):
            if collector._page.goto_calls:
                return recovered_payload
            return {"related_queries": [], "multiline_data": None, "raw_requests": []}

        collector._wait_for_capture = fake_wait
        collector._wait_for_capture_after_reload = fake_wait
        collector._prepare_explore_page = _noop_async
        collector._raise_if_blocked_page = _noop_async
        collector._refresh_if_stuck_loading = _noop_async
        collector._capture_dom_fallback = fake_dom

        result = await collector.capture(
            base_keyword="music",
            keywords=["song"],
            time_range="today 12-m",
        )

        assert result == recovered_payload
        assert collector._page.goto_calls

    asyncio.run(run())


def test_wait_for_capture_after_reload_returns_when_page_is_not_shell_only():
    async def run():
        collector = GoogleTrendsCollector(timeout_ms=100)
        collector._capture_state = _CaptureState(
            related_queries=[],
            multiline_data=None,
            raw_requests=[],
            blocked_error=None,
        )

        async def fake_shell_only() -> bool:
            return False

        collector._is_loading_shell_only = fake_shell_only
        await collector._wait_for_capture_after_reload(expected_related=1)

    asyncio.run(run())


def test_parse_dom_multiline_data_reads_timeline_rows():
    body = (
        "Interest over time\n"
        "Apr 13, 2025\t47\t56\t34\t5\n"
        "Apr 20, 2025\t50\t54\t34\t5\n"
        "Apr 27, 2025\t47\t57\t35\t5\n"
        "May 4, 2025\t48\t58\t36\t5\n"
        "May 11, 2025\t47\t58\t35\t5\n"
        "May 18, 2025\t48\t58\t35\t5\n"
        "May 25, 2025\t46\t56\t34\t5\n"
        "Jun 1, 2025\t48\t58\t34\t5\n"
        "Jun 8, 2025\t47\t60\t34\t5\n"
        "Jun 15, 2025\t50\t59\t36\t5\n"
    )
    payload = GoogleTrendsCollector._parse_dom_multiline_data(body)
    assert payload is not None
    assert len(payload["default"]["timelineData"]) == 10


def test_parse_dom_related_queries_reads_sections():
    body = (
        "image\n"
        "Related queries\n"
        "Analyze\n"
        "Rising\n"
        "1\n"
        "nano banana\n"
        "Breakout\n"
        "more_vert\n"
        "2\n"
        "ai news today\n"
        "Breakout\n"
        "more_vert\n"
        "Showing 1-5 of 19 queries\n"
        "photo\n"
        "Related queries\n"
        "1\n"
        "gemini ai photo\n"
        "Breakout\n"
        "more_vert\n"
        "Showing 1-5 of 24 queries\n"
    )
    related = GoogleTrendsCollector._parse_dom_related_queries(body, ["image", "photo"])
    assert len(related) == 2
    assert related[0]["keyword"] == "image"
    assert related[0]["payload"]["default"]["rankedList"][1]["rankedKeyword"][0]["query"] == "nano banana"


def test_is_loading_shell_only_detects_incomplete_page():
    async def run():
        collector = GoogleTrendsCollector()
        collector._page = _FakePage(
            _FakeResponse("https://trends.google.com/trends/explore?q=image", 200),
            body_text="Worldwide, Past 12 months\nInterest over time\nSearch term",
        )
        assert await collector._is_loading_shell_only() is True

    asyncio.run(run())


def test_is_loading_shell_only_detects_loaded_data_sections():
    async def run():
        collector = GoogleTrendsCollector()
        collector._page = _FakePage(
            _FakeResponse("https://trends.google.com/trends/explore?q=image", 200),
            body_text="Worldwide, Past 12 months\nInterest over time\nRelated queries\nShowing 1-5 of 19 queries",
        )
        assert await collector._is_loading_shell_only() is False

    asyncio.run(run())


async def _noop_async(*args, **kwargs):
    return None
