"""
Google Ads Transparency Center Scraper - FastAPI Backend
========================================================
部署方式：
  1. pip install -r requirements.txt
  2. playwright install chromium
  3. uvicorn main:app --host 0.0.0.0 --port 8000

API 端点：
  POST /api/search  { "domain": "example.com", "region": "anywhere", "max_scroll_pages": 10 }
  GET  /api/health
"""

import asyncio
import json
import re
import uuid
from dataclasses import dataclass, field, asdict
from typing import Optional
from urllib.parse import quote
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from playwright.async_api import async_playwright, Page, BrowserContext, Response

# ─────────────────────────────────────────────
# Data Models
# ─────────────────────────────────────────────
@dataclass
class AdvertiserInfo:
    advertiser_id: str = ""
    name: str = ""
    url: str = ""
    region: str = ""

@dataclass
class AdCreative:
    creative_id: str = ""
    advertiser_id: str = ""
    advertiser_name: str = ""
    target_domain: str = ""
    format: str = ""
    first_shown: str = ""
    last_shown: str = ""

@dataclass
class ScrapeResult:
    query_domain: str = ""
    advertisers: list = field(default_factory=list)
    all_domains: list = field(default_factory=list)
    ad_creatives: list = field(default_factory=list)
    total_ads_found: int = 0

# ─────────────────────────────────────────────
# Core Scraper (from original script)
# ─────────────────────────────────────────────
class GoogleAdsTransparencyScraper:
    BASE_URL = "https://adstransparency.google.com"

    def __init__(self, headless=True, proxy=None, region="anywhere", max_scroll_pages=10, timeout=30000):
        self.headless = headless
        self.proxy = proxy
        self.region = region
        self.max_scroll_pages = max_scroll_pages
        self.timeout = timeout
        self._browser = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._intercepted_responses: list[dict] = []

    async def start(self):
        pw = await async_playwright().start()
        launch_opts = {"headless": self.headless}
        if self.proxy:
            launch_opts["proxy"] = {"server": self.proxy}
        self._browser = await pw.chromium.launch(**launch_opts)
        self._context = await self._browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            locale="en-US",
        )
        self._page = await self._context.new_page()
        self._page.set_default_timeout(self.timeout)
        self._page.on("response", self._on_response)

    async def close(self):
        if self._browser:
            await self._browser.close()

    async def _on_response(self, response: Response):
        url = response.url
        if "batchexecute" in url or "TransparencyReport" in url:
            try:
                body = await response.text()
                self._intercepted_responses.append({"url": url, "status": response.status, "body": body})
            except Exception:
                pass

    @staticmethod
    def _extract_json_blocks(text: str) -> list:
        results = []
        text = text.replace(")]}'", "").strip()
        lines = text.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.isdigit():
                json_candidate = ""
                j = i + 1
                while j < len(lines):
                    json_candidate += lines[j] + "\n"
                    try:
                        parsed = json.loads(json_candidate)
                        results.append(parsed)
                        i = j + 1
                        break
                    except json.JSONDecodeError:
                        j += 1
                else:
                    i += 1
            else:
                try:
                    parsed = json.loads(line)
                    if isinstance(parsed, list):
                        results.append(parsed)
                except json.JSONDecodeError:
                    pass
                i += 1
        return results

    async def _extract_advertiser_from_dom(self) -> list[AdvertiserInfo]:
        advertisers = []
        try:
            await self._page.wait_for_selector('a[href*="/advertiser/AR"]', timeout=15000)
        except Exception:
            pass
        links = await self._page.query_selector_all('a[href*="/advertiser/AR"]')
        seen_ids = set()
        for link in links:
            href = await link.get_attribute("href") or ""
            text = (await link.inner_text()).strip()
            match = re.search(r"/advertiser/(AR\d+)", href)
            if match:
                adv_id = match.group(1)
                if adv_id not in seen_ids:
                    seen_ids.add(adv_id)
                    advertisers.append(AdvertiserInfo(
                        advertiser_id=adv_id,
                        name=text if text else "Unknown",
                        url=f"{self.BASE_URL}/advertiser/{adv_id}?region={self.region}",
                    ))
        if not advertisers:
            page_content = await self._page.content()
            for match in re.finditer(r'advertiser/(AR\d+)', page_content):
                adv_id = match.group(1)
                if adv_id not in seen_ids:
                    seen_ids.add(adv_id)
                    advertisers.append(AdvertiserInfo(
                        advertiser_id=adv_id, name="",
                        url=f"{self.BASE_URL}/advertiser/{adv_id}?region={self.region}",
                    ))
        return advertisers

    async def _extract_domains_from_dom(self) -> set[str]:
        domains = set()
        try:
            await self._page.wait_for_selector(
                'creative-preview, .creative-card, [class*="creative"], [class*="ad-card"]', timeout=15000)
        except Exception:
            pass
        page_text = await self._page.inner_text("body")
        domain_pattern = r'(?:[\w-]+\.)+(?:com|net|org|io|ai|co|app|dev|xyz|info|biz|me|us|uk|de|fr|cn|jp|ru|edu|gov)(?:\.\w{2})?'
        exclude = {"google.com", "adstransparency.google.com", "gstatic.com", "googleapis.com", "googlesyndication.com", "googleusercontent.com"}
        for match in re.finditer(domain_pattern, page_text):
            domain = match.group(0).lower()
            if domain not in exclude:
                domains.add(domain)
        page_html = await self._page.content()
        for match in re.finditer(r'target[_-]?domain["\s:=]+["\']?([\w.-]+)', page_html, re.I):
            domains.add(match.group(1).lower())
        return domains

    async def _extract_advertiser_name_from_dom(self) -> str:
        """Extract advertiser name from DOM with improved selector priority."""
        # Priority order: most specific selectors first
        selectors = [
            '[class*="advertiser-name"]',
            '[class*="advertiser"] [class*="name"]',
            '[class*="header"] [class*="title"]',
            'h1',
            'h2',
        ]
        exclude_texts = {"Ads Transparency Center", "Advertiser Details", "Home", "FAQ", "Sign in"}

        try:
            for sel in selectors:
                elements = await self._page.query_selector_all(sel)
                for el in elements:
                    text = (await el.inner_text()).strip()
                    # Skip empty, too long, or excluded texts
                    if text and 2 < len(text) < 200 and text not in exclude_texts:
                        # Skip if it looks like a navigation item
                        if not any(skip in text.lower() for skip in ["arrow", "keyboard", "calendar", "search"]):
                            return text
        except Exception:
            pass
        return ""

    async def _extract_creatives_from_dom(self, advertiser_id: str) -> list[AdCreative]:
        """Extract ad creatives from DOM elements."""
        creatives = []
        seen_ids = set()

        # Look for creative links in the page
        creative_selectors = [
            'a[href*="/creative/CR"]',
            'a[href*="creative"][href*="AR"]',
            '[class*="creative"] a',
            '[class*="ad-card"] a',
        ]

        for sel in creative_selectors:
            try:
                elements = await self._page.query_selector_all(sel)
                for el in elements:
                    href = await el.get_attribute("href") or ""
                    # Extract creative ID from URL
                    cr_match = re.search(r'/creative/(CR\d+)', href)
                    ar_match = re.search(r'/advertiser/(AR\d+)', href)

                    if cr_match:
                        cr_id = cr_match.group(1)
                        if cr_id not in seen_ids:
                            seen_ids.add(cr_id)
                            # Try to extract target domain from link text or nearby elements
                            text = (await el.inner_text()).strip()
                            creatives.append(AdCreative(
                                creative_id=cr_id,
                                advertiser_id=ar_match.group(1) if ar_match else advertiser_id,
                                target_domain=self._extract_domain_from_text(text),
                            ))
            except Exception:
                pass

        # Also search in page HTML for creative IDs
        page_html = await self._page.content()
        for match in re.finditer(r'/creative/(CR\d{15,25})', page_html):
            cr_id = match.group(1)
            if cr_id not in seen_ids:
                seen_ids.add(cr_id)
                creatives.append(AdCreative(
                    creative_id=cr_id,
                    advertiser_id=advertiser_id,
                ))

        return creatives

    def _extract_domain_from_text(self, text: str) -> str:
        """Extract a domain from text content."""
        domain_pattern = r'(?:[\w-]+\.)+(?:com|net|org|io|ai|co|app|dev|xyz|info|biz|me|us|uk|de|fr|cn|jp|ru|edu|gov)(?:\.\w{2})?'
        match = re.search(domain_pattern, text, re.I)
        return match.group(0).lower() if match else ""

    async def _extract_domains_from_creative_links(self, advertiser_id: str) -> set[str]:
        """Navigate to creative detail pages to extract target domains."""
        domains = set()

        # Find all creative links
        creative_links = await self._page.query_selector_all('a[href*="/creative/CR"]')
        if not creative_links:
            # Try alternative selectors
            creative_links = await self._page.query_selector_all('a[href*="creative"]')

        # Only check first few creatives to avoid too many navigations
        for link in creative_links[:3]:
            try:
                href = await link.get_attribute("href") or ""
                if "/creative/" in href:
                    # Build full URL
                    if href.startswith("/"):
                        creative_url = f"{self.BASE_URL}{href}"
                    else:
                        creative_url = href

                    # Navigate to creative page
                    current_url = self._page.url
                    await self._page.goto(creative_url, wait_until="networkidle", timeout=15000)
                    await asyncio.sleep(2)

                    # Extract domain from page content
                    page_text = await self._page.inner_text("body")
                    page_html = await self._page.content()

                    # Look for target URL/domain patterns
                    url_patterns = [
                        r'https?://([^\s/"<>]+)',
                        r'target[_-]?url["\s:=]+["\']?([^\s"\'<>]+)',
                        r'landing[_-]?page["\s:=]+["\']?([^\s"\'<>]+)',
                        r'destination[_-]?url["\s:=]+["\']?([^\s"\'<>]+)',
                    ]

                    for pattern in url_patterns:
                        for match in re.finditer(pattern, page_html, re.I):
                            domain = match.group(1).lower()
                            # Clean up domain
                            domain = re.sub(r'^www\.', '', domain)
                            domain = domain.split('/')[0]
                            if domain and not any(d in domain for d in ["google", "gstatic", "youtube"]):
                                domains.add(domain)

                    # Go back to advertiser page
                    await self._page.goto(current_url, wait_until="networkidle", timeout=15000)
                    await asyncio.sleep(1)
            except Exception:
                pass

        return domains

    async def _scroll_to_load_all(self, max_pages=None):
        max_pages = max_pages or self.max_scroll_pages
        prev_height = 0
        for i in range(max_pages):
            await self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(2)
            curr_height = await self._page.evaluate("document.body.scrollHeight")
            if curr_height == prev_height:
                break
            prev_height = curr_height

    def _parse_advertiser_from_intercepted(self) -> list[AdvertiserInfo]:
        advertisers = []
        seen_ids = set()
        for resp in self._intercepted_responses:
            body = resp.get("body", "")
            for match in re.finditer(r'"(AR\d{15,25})"', body):
                adv_id = match.group(1)
                if adv_id not in seen_ids:
                    seen_ids.add(adv_id)
                    name = ""
                    start = max(0, match.start() - 300)
                    end = min(len(body), match.end() + 300)
                    context = body[start:end]
                    for pat in [rf'"{adv_id}"\s*,\s*"([^"]+)"', rf'"([^"]+)"\s*,\s*"{adv_id}"']:
                        name_match = re.search(pat, context)
                        if name_match:
                            candidate = name_match.group(1)
                            if len(candidate) < 100 and not candidate.startswith(("AR", "CR", "http")):
                                name = candidate
                                break
                    advertisers.append(AdvertiserInfo(
                        advertiser_id=adv_id, name=name,
                        url=f"{self.BASE_URL}/advertiser/{adv_id}?region={self.region}",
                    ))
        return advertisers

    def _parse_domains_from_intercepted(self) -> set[str]:
        domains = set()
        domain_pattern = r'(?:[\w-]+\.)+(?:com|net|org|io|ai|co|app|dev|xyz|info|biz|me|us|uk|de|fr|cn|jp|ru|edu|gov)(?:\.\w{2})?'
        google_domains = {"google.com", "googleapis.com", "gstatic.com", "googlesyndication.com",
                          "googleusercontent.com", "googleadservices.com", "google.co", "google.com.au",
                          "doubleclick.net", "youtube.com", "ggpht.com", "displayads.googleusercontent.com"}
        for resp in self._intercepted_responses:
            body = resp.get("body", "")
            for match in re.finditer(domain_pattern, body):
                domain = match.group(0).lower()
                if not any(domain.endswith(gd) or domain == gd for gd in google_domains):
                    domains.add(domain)
        return domains

    def _parse_creatives_from_intercepted(self, advertiser_id: str) -> list[AdCreative]:
        creatives = []
        seen_ids = set()
        for resp in self._intercepted_responses:
            body = resp.get("body", "")
            for match in re.finditer(r'"(CR\d{15,25})"', body):
                cr_id = match.group(1)
                if cr_id not in seen_ids:
                    seen_ids.add(cr_id)
                    creatives.append(AdCreative(creative_id=cr_id, advertiser_id=advertiser_id))
        return creatives

    async def search_domain(self, domain: str) -> ScrapeResult:
        result = ScrapeResult(query_domain=domain)
        search_url = f"{self.BASE_URL}/?region={self.region}&domain={quote(domain)}"
        self._intercepted_responses.clear()
        try:
            await self._page.goto(search_url, wait_until="networkidle", timeout=self.timeout)
        except Exception:
            pass
        await asyncio.sleep(5)

        advertisers_from_api = self._parse_advertiser_from_intercepted()
        advertisers_from_dom = await self._extract_advertiser_from_dom()

        seen_ids = set()
        all_advertisers = []
        for adv in advertisers_from_api + advertisers_from_dom:
            if adv.advertiser_id and adv.advertiser_id not in seen_ids:
                seen_ids.add(adv.advertiser_id)
                all_advertisers.append(adv)

        if not all_advertisers:
            return result

        all_domains = set()
        all_creatives = []
        for adv in all_advertisers:
            adv_url = adv.url or f"{self.BASE_URL}/advertiser/{adv.advertiser_id}?region={self.region}"
            self._intercepted_responses.clear()
            try:
                await self._page.goto(adv_url, wait_until="networkidle", timeout=self.timeout)
            except Exception:
                pass
            await asyncio.sleep(5)

            # Extract advertiser name if not already known or is placeholder
            if not adv.name or adv.name == "Unknown":
                adv.name = await self._extract_advertiser_name_from_dom()

            # Scroll to load more content
            await self._scroll_to_load_all()

            # Extract domains from multiple sources
            domains_from_api = self._parse_domains_from_intercepted()
            domains_from_dom = await self._extract_domains_from_dom()
            domains_from_creatives = await self._extract_domains_from_creative_links(adv.advertiser_id)

            adv_domains = domains_from_api | domains_from_dom | domains_from_creatives
            all_domains.update(adv_domains)

            # Extract creatives from multiple sources
            creatives_from_api = self._parse_creatives_from_intercepted(adv.advertiser_id)
            creatives_from_dom = await self._extract_creatives_from_dom(adv.advertiser_id)

            # Merge creatives, preferring ones with more info
            seen_cr_ids = {c.creative_id for c in all_creatives}
            for cr in creatives_from_api + creatives_from_dom:
                if cr.creative_id not in seen_cr_ids:
                    seen_cr_ids.add(cr.creative_id)
                    cr.advertiser_name = adv.name
                    all_creatives.append(cr)

        # Add query domain to results if not already present
        all_domains.add(domain.lower())

        # Convert advertisers to dict AFTER names have been extracted
        result.advertisers = [asdict(a) for a in all_advertisers]
        result.all_domains = sorted(all_domains)
        result.ad_creatives = [asdict(c) for c in all_creatives]
        result.total_ads_found = len(all_creatives)
        return result

# ─────────────────────────────────────────────
# FastAPI App
# ─────────────────────────────────────────────
app = FastAPI(
    title="Google Ads Transparency Scraper API",
    description="查询域名在 Google Ads Transparency Center 的广告主和关联域名",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SearchRequest(BaseModel):
    domain: str = Field(..., description="要查询的域名", examples=["aiimagetovideo.ai"])
    region: str = Field(default="anywhere", description="区域过滤")
    max_scroll_pages: int = Field(default=10, ge=1, le=50, description="最大滚动页数")
    proxy: Optional[str] = Field(default=None, description="代理地址")
    timeout: int = Field(default=30000, ge=5000, le=120000, description="超时时间(ms)")

class SearchResponse(BaseModel):
    success: bool
    task_id: str
    data: Optional[dict] = None
    error: Optional[str] = None
    duration_seconds: float = 0

# 任务存储（生产环境应使用 Redis 等）
tasks: dict = {}

@app.get("/api/health")
async def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}

@app.post("/api/search", response_model=SearchResponse)
async def search_domain(req: SearchRequest):
    """同步执行域名查询（注意：查询可能需要 1-3 分钟）"""
    task_id = str(uuid.uuid4())[:8]
    start_time = asyncio.get_event_loop().time()

    scraper = GoogleAdsTransparencyScraper(
        headless=True,
        proxy=req.proxy,
        region=req.region,
        max_scroll_pages=req.max_scroll_pages,
        timeout=req.timeout,
    )

    try:
        await scraper.start()
        result = await scraper.search_domain(req.domain)
        duration = asyncio.get_event_loop().time() - start_time
        return SearchResponse(
            success=True,
            task_id=task_id,
            data=asdict(result),
            duration_seconds=round(duration, 2),
        )
    except Exception as e:
        duration = asyncio.get_event_loop().time() - start_time
        return SearchResponse(
            success=False,
            task_id=task_id,
            error=str(e),
            duration_seconds=round(duration, 2),
        )
    finally:
        await scraper.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
