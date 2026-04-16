from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from playwright.async_api import Browser, BrowserContext, Page, async_playwright


def _slugify(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-") or "target"


@dataclass
class CapturedRequest:
    url: str
    method: str
    resource_type: str
    post_data: str | None = None


@dataclass
class CapturedResponse:
    url: str
    status: int
    resource_type: str
    content_type: str
    body_preview: str


@dataclass
class ProbeSummary:
    target: str
    mode: str
    page_url: str
    page_title: str
    clicked: bool
    input_value: str | None
    button_texts: list[str]
    result_indicators: list[str]
    cloudflare_requests: list[CapturedRequest]
    api_requests: list[CapturedRequest]
    api_responses: list[CapturedResponse]
    console_tail: list[dict[str, str]]
    page_errors: list[str]
    screenshot_path: str
    html_path: str
    requests_path: str
    responses_path: str


class AhrefsTrafficProbe:
    def __init__(
        self,
        *,
        target: str,
        mode: str,
        output_dir: Path,
        headless: bool,
        timeout_ms: int,
        post_click_wait_ms: int,
        browser_cdp_url: str | None,
    ) -> None:
        self.target = target
        self.mode = mode
        self.output_dir = output_dir
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.post_click_wait_ms = post_click_wait_ms
        self.browser_cdp_url = browser_cdp_url
        self._requests: list[CapturedRequest] = []
        self._responses: list[CapturedResponse] = []
        self._console_logs: list[dict[str, str]] = []
        self._page_errors: list[str] = []

    async def run(self) -> ProbeSummary:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        async with async_playwright() as p:
            browser, context, owns_browser, owns_context = await self._open_browser(p)
            try:
                page = await context.new_page()
                page.set_default_timeout(self.timeout_ms)
                page.on("request", self._on_request)
                page.on("response", lambda resp: asyncio.create_task(self._on_response(resp)))
                page.on("console", lambda msg: self._console_logs.append({"type": msg.type, "text": msg.text}))
                page.on("pageerror", lambda exc: self._page_errors.append(str(exc)))

                url = self._build_url()
                await page.goto(url, wait_until="domcontentloaded")
                await page.wait_for_timeout(4000)

                input_value = await self._prefill_input(page)
                button_texts = await page.locator("button").all_text_contents()
                button = page.get_by_role("button", name=re.compile(r"Check traffic", re.I))

                self._requests.clear()
                self._responses.clear()
                clicked = False
                try:
                    await button.click()
                    clicked = True
                except Exception:
                    clicked = False

                await page.wait_for_timeout(self.post_click_wait_ms)
                await self._save_artifacts(page)
                result_indicators = await self._extract_result_indicators(page)

                slug = _slugify(self.target)
                return ProbeSummary(
                    target=self.target,
                    mode=self.mode,
                    page_url=page.url,
                    page_title=await page.title(),
                    clicked=clicked,
                    input_value=input_value,
                    button_texts=button_texts[:20],
                    result_indicators=result_indicators,
                    cloudflare_requests=[
                        req for req in self._requests if "cloudflare" in req.url or "/cdn-cgi/" in req.url
                    ],
                    api_requests=[
                        req
                        for req in self._requests
                        if ("ahrefs.com" in req.url or "api" in req.url)
                        and "cloudflare" not in req.url
                        and "/cdn-cgi/" not in req.url
                    ],
                    api_responses=[
                        resp
                        for resp in self._responses
                        if ("ahrefs.com" in resp.url or "api" in resp.url)
                        and "cloudflare" not in resp.url
                        and "/cdn-cgi/" not in resp.url
                    ],
                    console_tail=self._console_logs[-20:],
                    page_errors=self._page_errors[-20:],
                    screenshot_path=str(self.output_dir / f"{slug}.png"),
                    html_path=str(self.output_dir / f"{slug}.html"),
                    requests_path=str(self.output_dir / f"{slug}.requests.json"),
                    responses_path=str(self.output_dir / f"{slug}.responses.json"),
                )
            finally:
                if owns_context:
                    await context.close()
                if owns_browser and browser is not None:
                    await browser.close()

    async def _open_browser(self, playwright) -> tuple[Browser | None, BrowserContext, bool, bool]:
        if self.browser_cdp_url:
            browser = await playwright.chromium.connect_over_cdp(self.browser_cdp_url)
            existing_context = browser.contexts[0] if browser.contexts else None
            context = existing_context or await browser.new_context()
            return browser, context, False, existing_context is None

        browser = await playwright.chromium.launch(headless=self.headless)
        context = await browser.new_context(viewport={"width": 1440, "height": 1100}, locale="en-US")
        return browser, context, True, True

    def _build_url(self) -> str:
        query = urlencode({"input": self.target, "mode": self.mode})
        return f"https://ahrefs.com/traffic-checker/?{query}"

    async def _prefill_input(self, page: Page) -> str | None:
        input_locator = page.locator('input[placeholder="Enter domain or URL"]').first
        if await input_locator.count() == 0:
            return None
        await input_locator.fill(self.target)
        return await input_locator.input_value()

    def _on_request(self, request) -> None:
        self._requests.append(
            CapturedRequest(
                url=request.url,
                method=request.method,
                resource_type=request.resource_type,
                post_data=(request.post_data[:1000] if request.post_data else None),
            )
        )

    async def _on_response(self, response) -> None:
        request = response.request
        content_type = (response.headers.get("content-type") or "").lower()
        if request.resource_type not in {"xhr", "fetch"} and "json" not in content_type:
            return
        try:
            body_preview = (await response.text())[:2000]
        except Exception:
            body_preview = ""
        self._responses.append(
            CapturedResponse(
                url=response.url,
                status=response.status,
                resource_type=request.resource_type,
                content_type=content_type,
                body_preview=body_preview,
            )
        )

    async def _save_artifacts(self, page: Page) -> None:
        slug = _slugify(self.target)
        html_path = self.output_dir / f"{slug}.html"
        screenshot_path = self.output_dir / f"{slug}.png"
        requests_path = self.output_dir / f"{slug}.requests.json"
        responses_path = self.output_dir / f"{slug}.responses.json"

        html_path.write_text(await page.content(), encoding="utf-8")
        await page.screenshot(path=str(screenshot_path), full_page=True)
        requests_path.write_text(
            json.dumps([asdict(item) for item in self._requests], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        responses_path.write_text(
            json.dumps([asdict(item) for item in self._responses], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    async def _extract_result_indicators(self, page: Page) -> list[str]:
        matches: list[str] = []
        body_text = await page.locator("body").inner_text()
        for pattern in [
            r"Top keywords.{0,120}",
            r"Organic keywords.{0,120}",
            r"Traffic by location.{0,120}",
            r"lovable\.dev.{0,120}",
            r"Unable to check traffic.{0,120}",
            r"Just a moment.{0,120}",
        ]:
            found = re.findall(pattern, body_text, flags=re.I | re.S)
            matches.extend(item.replace("\n", " ")[:180] for item in found[:3])
        return matches


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Probe Ahrefs traffic-checker with Playwright.")
    parser.add_argument("target", help="Domain to query, for example lovable.dev")
    parser.add_argument("--mode", default="subdomains", help="Traffic checker mode. Default: subdomains")
    parser.add_argument(
        "--output-dir",
        default=str(Path(__file__).resolve().parents[1] / "artifacts" / "ahrefs_probe"),
        help="Directory for screenshots and captured payloads.",
    )
    parser.add_argument("--headless", action="store_true", help="Run headless Chromium instead of visible mode.")
    parser.add_argument("--timeout-ms", type=int, default=30000, help="Page timeout in milliseconds.")
    parser.add_argument("--post-click-wait-ms", type=int, default=12000, help="Wait after clicking the button.")
    parser.add_argument("--browser-cdp-url", default=None, help="Optional Chrome DevTools endpoint.")
    return parser


async def _async_main(args: argparse.Namespace) -> int:
    probe = AhrefsTrafficProbe(
        target=args.target,
        mode=args.mode,
        output_dir=Path(args.output_dir),
        headless=args.headless,
        timeout_ms=args.timeout_ms,
        post_click_wait_ms=args.post_click_wait_ms,
        browser_cdp_url=args.browser_cdp_url,
    )
    summary = await probe.run()
    print(json.dumps(asdict(summary), ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return asyncio.run(_async_main(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
