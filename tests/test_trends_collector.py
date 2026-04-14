import asyncio

import pytest

from app.collectors.trends_collector import GoogleTrendsCollector, TrendsCollectorError, _CaptureState


class _FakeLocator:
    def __init__(self, text: str):
        self._text = text

    async def inner_text(self) -> str:
        return self._text


class _FakePage:
    def __init__(self, response, title: str = "", body_text: str = ""):
        self._response = response
        self._title = title
        self._body_text = body_text

    async def goto(self, url: str, wait_until: str = "domcontentloaded"):
        return self._response

    async def title(self) -> str:
        return self._title

    def locator(self, selector: str):
        assert selector == "body"
        return _FakeLocator(self._body_text)


class _FakeResponse:
    def __init__(self, url: str, status: int, text: str = ""):
        self.url = url
        self.status = status
        self._text = text

    async def text(self) -> str:
        return self._text


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
