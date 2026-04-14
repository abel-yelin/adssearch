import asyncio
import html
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Optional
from urllib.parse import parse_qs, quote, unquote, urlparse

from playwright.async_api import BrowserContext, Page, Response, async_playwright


@dataclass
class AdvertiserInfo:
    advertiser_id: str = ""
    name: str = ""
    url: str = ""
    region: str = ""
    matched_domains: list = field(default_factory=list)
    other_domains: list = field(default_factory=list)
    has_query_domain: bool = False


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
    other_domains: list = field(default_factory=list)
    ad_creatives: list = field(default_factory=list)
    total_ads_found: int = 0
    has_ads: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


class GoogleAdsTransparencyScraper:
    BASE_URL = "https://adstransparency.google.com"
    DOMAIN_PATTERN = re.compile(
        r"(?:https?://)?(?:www\d?\.)?(?:[a-z0-9][a-z0-9-]*\.)+[a-z]{2,24}",
        re.I,
    )
    NOISE_EXACT_DOMAINS = {
        "google.com",
        "googleapis.com",
        "gstatic.com",
        "googlesyndication.com",
        "googleusercontent.com",
        "googleadservices.com",
        "doubleclick.net",
        "youtube.com",
        "youtu.be",
        "ytimg.com",
        "ggpht.com",
        "w3.org",
        "schema.org",
    }
    NOISE_SUFFIX_DOMAINS = {
        "google.com",
        "googleapis.com",
        "gstatic.com",
        "googlesyndication.com",
        "googleusercontent.com",
        "googleadservices.com",
        "doubleclick.net",
        "youtube.com",
        "ytimg.com",
        "ggpht.com",
    }
    COMMON_SECOND_LEVEL_SUFFIXES = {
        "co.uk", "org.uk", "gov.uk", "ac.uk",
        "com.au", "net.au", "org.au",
        "com.br", "com.mx", "com.tr", "com.cn", "com.hk", "com.tw",
        "co.jp", "ne.jp", "or.jp",
        "co.kr", "or.kr",
        "co.in", "firm.in", "net.in", "org.in",
    }

    def __init__(
        self,
        headless: bool = True,
        proxy: Optional[str] = None,
        region: str = "anywhere",
        max_scroll_pages: int = 10,
        timeout: int = 30000,
    ):
        self.headless = headless
        self.proxy = proxy
        self.region = region
        self.max_scroll_pages = max_scroll_pages
        self.timeout = timeout
        self._playwright = None
        self._browser = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._intercepted_responses: list[dict] = []

    async def start(self):
        self._playwright = await async_playwright().start()
        launch_opts = {"headless": self.headless}
        if self.proxy:
            launch_opts["proxy"] = {"server": self.proxy}
        self._browser = await self._playwright.chromium.launch(**launch_opts)
        self._context = await self._browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            locale="en-US",
        )
        self._page = await self._context.new_page()
        self._page.set_default_timeout(self.timeout)
        self._page.on("response", self._on_response)

    async def close(self):
        if self._context:
            await self._context.close()
            self._context = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    async def _on_response(self, response: Response):
        if "batchexecute" not in response.url and "TransparencyReport" not in response.url:
            return
        try:
            body = await response.text()
            self._intercepted_responses.append(
                {"url": response.url, "status": response.status, "body": body}
            )
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
                        results.append(json.loads(json_candidate))
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
            if not match:
                continue
            adv_id = match.group(1)
            if adv_id in seen_ids:
                continue
            seen_ids.add(adv_id)
            advertisers.append(
                AdvertiserInfo(
                    advertiser_id=adv_id,
                    name=text if text else "Unknown",
                    url=f"{self.BASE_URL}/advertiser/{adv_id}?region={self.region}",
                )
            )

        if advertisers:
            return advertisers

        page_content = await self._page.content()
        for match in re.finditer(r"advertiser/(AR\d+)", page_content):
            adv_id = match.group(1)
            if adv_id in seen_ids:
                continue
            seen_ids.add(adv_id)
            advertisers.append(
                AdvertiserInfo(
                    advertiser_id=adv_id,
                    name="",
                    url=f"{self.BASE_URL}/advertiser/{adv_id}?region={self.region}",
                )
            )
        return advertisers

    async def _extract_domains_from_dom(self) -> set[str]:
        try:
            await self._page.wait_for_selector(
                'creative-preview, .creative-card, [class*="creative"], [class*="ad-card"]',
                timeout=15000,
            )
        except Exception:
            pass
        page_html = await self._page.content()
        return self._extract_contextual_domains(page_html)

    async def _extract_advertiser_name_from_dom(self) -> str:
        selectors = [
            '[aria-label*="Legal name"]',
            '[class*="advertiser-name"]',
            '[class*="advertiser"] [class*="name"]',
            '[class*="header"] [class*="title"]',
            "h1",
            "h2",
        ]
        exclude_texts = {"Ads Transparency Center", "Advertiser Details", "Home", "FAQ", "Sign in"}

        try:
            for selector in selectors:
                elements = await self._page.query_selector_all(selector)
                for element in elements:
                    text = (await element.inner_text()).strip()
                    if not text or len(text) <= 2 or len(text) >= 200:
                        continue
                    if text in exclude_texts:
                        continue
                    if any(skip in text.lower() for skip in ["arrow", "keyboard", "calendar", "search"]):
                        continue
                    if "Legal name:" in text:
                        text = text.split("Legal name:", 1)[1].split("\n", 1)[0].strip()
                    if "\n" in text and len(text.splitlines()[0].strip()) > 2:
                        text = text.splitlines()[0].strip()
                    return text
        except Exception:
            pass
        body_text = await self._page.text_content("body") or ""
        match = re.search(r"Legal name:\s*([^\n]+)", body_text, re.I)
        if match:
            return match.group(1).strip()
        match = re.search(r"keyboard_arrow_right\s*([^\n]+)", body_text)
        if match:
            return match.group(1).strip()
        return ""

    async def _extract_creatives_from_dom(self, advertiser_id: str) -> list[AdCreative]:
        creatives = []
        seen_ids = set()
        selectors = [
            'a[href*="/creative/CR"]',
            'a[href*="creative"][href*="AR"]',
            '[class*="creative"] a',
            '[class*="ad-card"] a',
        ]

        for selector in selectors:
            try:
                elements = await self._page.query_selector_all(selector)
                for element in elements:
                    href = await element.get_attribute("href") or ""
                    cr_match = re.search(r"/creative/(CR\d+)", href)
                    ar_match = re.search(r"/advertiser/(AR\d+)", href)
                    if not cr_match:
                        continue
                    cr_id = cr_match.group(1)
                    if cr_id in seen_ids:
                        continue
                    seen_ids.add(cr_id)
                    text = (await element.inner_text()).strip()
                    outer_html = await element.evaluate("(node) => node.outerHTML")
                    creatives.append(
                        AdCreative(
                            creative_id=cr_id,
                            advertiser_id=ar_match.group(1) if ar_match else advertiser_id,
                            target_domain=self._extract_domain_from_text(text),
                            format=self._infer_creative_format(text, outer_html),
                        )
                    )
            except Exception:
                pass

        page_html = await self._page.content()
        for match in re.finditer(r"/creative/(CR\d{15,25})", page_html):
            cr_id = match.group(1)
            if cr_id in seen_ids:
                continue
            seen_ids.add(cr_id)
            creatives.append(
                AdCreative(
                    creative_id=cr_id,
                    advertiser_id=advertiser_id,
                    format=self._infer_creative_format("", page_html, creative_id=cr_id),
                )
            )

        return creatives

    def _extract_domain_from_text(self, text: str) -> str:
        match = self.DOMAIN_PATTERN.search(text)
        return self._normalize_domain(match.group(0)) if match else ""

    def _normalize_domain(self, raw_value: str) -> str:
        if not raw_value:
            return ""

        value = raw_value.strip().strip('''"'`[](){}<>,;''').lower()
        if not value:
            return ""

        if "://" not in value:
            value = f"//{value}"

        try:
            parsed = urlparse(value)
        except ValueError:
            return ""
        host = (parsed.hostname or "").strip(".").lower()
        if not host or host == "localhost":
            return ""
        if re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", host):
            return ""

        host = re.sub(r"^www\d?\.", "", host)
        labels = host.split(".")
        if len(labels) < 2:
            return ""

        for label in labels:
            if not re.fullmatch(r"[a-z0-9-]{1,63}", label):
                return ""
            if label.startswith("-") or label.endswith("-"):
                return ""

        registrable = self._to_registrable_domain(host)
        if not registrable or self._is_noise_domain(registrable):
            return ""
        return registrable

    def _to_registrable_domain(self, host: str) -> str:
        parts = host.split(".")
        if len(parts) < 2:
            return ""
        suffix2 = ".".join(parts[-2:])
        if suffix2 in self.COMMON_SECOND_LEVEL_SUFFIXES and len(parts) >= 3:
            return ".".join(parts[-3:])
        return suffix2

    def _is_noise_domain(self, domain: str) -> bool:
        if domain in self.NOISE_EXACT_DOMAINS:
            return True
        return any(
            domain == suffix or domain.endswith(f".{suffix}")
            for suffix in self.NOISE_SUFFIX_DOMAINS
        )

    def _extract_contextual_domains(self, text: str) -> set[str]:
        domains = set()
        expanded_text = html.unescape(text or "")
        expanded_text = (
            expanded_text.replace("\\u0026", "&")
            .replace("\\x26", "&")
            .replace("\\x3d", "=")
            .replace("\\/", "/")
        )
        patterns = [
            r'target[_-]?(?:url|domain|page)["\s:=]+["\']?([^\s"\'<>]+)',
            r'landing[_-]?(?:url|domain|page)["\s:=]+["\']?([^\s"\'<>]+)',
            r'destination[_-]?(?:url|domain|page)["\s:=]+["\']?([^\s"\'<>]+)',
            r'display[_-]?(?:url|domain)["\s:=]+["\']?([^\s"\'<>]+)',
            r'final[_-]?(?:url|domain)["\s:=]+["\']?([^\s"\'<>]+)',
            r'"(https?://[^"<>]+)"',
            r"(https?://[^\s'\"<>]+)",
            r"adurl=([^&\\\"'\\s>]+)",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, expanded_text, re.I):
                raw_value = unquote(match.group(1))
                domain = self._normalize_domain(raw_value)
                if domain:
                    domains.add(domain)

        for url_match in re.finditer(r"https?://[^\s'\"<>]+", expanded_text, re.I):
            url = url_match.group(0)
            try:
                parsed = urlparse(url)
            except ValueError:
                continue
            adurl_values = parse_qs(parsed.query).get("adurl") or []
            for raw_value in adurl_values:
                domain = self._normalize_domain(unquote(raw_value))
                if domain:
                    domains.add(domain)
        return domains

    async def _extract_creative_details_from_links(self, advertiser_id: str) -> dict[str, dict[str, str]]:
        details: dict[str, dict[str, str]] = {}
        creative_links = await self._page.query_selector_all('a[href*="/creative/CR"]')
        if not creative_links:
            creative_links = await self._page.query_selector_all('a[href*="creative"]')

        for link in creative_links[:3]:
            try:
                href = await link.get_attribute("href") or ""
                if "/creative/" not in href:
                    continue
                creative_match = re.search(r"/creative/(CR\d+)", href)
                if not creative_match:
                    continue
                creative_id = creative_match.group(1)
                link_text = (await link.inner_text()).strip()
                outer_html = await link.evaluate("(node) => node.outerHTML")

                creative_url = f"{self.BASE_URL}{href}" if href.startswith("/") else href
                detail_page = await self._context.new_page()
                detail_page.set_default_timeout(15000)
                try:
                    await detail_page.goto(creative_url, wait_until="domcontentloaded", timeout=15000)
                    await asyncio.sleep(2)
                    page_html = await detail_page.content()
                    body_text = await detail_page.text_content("body") or ""
                    detail_domains = self._extract_contextual_domains(page_html) | self._extract_contextual_domains(body_text)
                    target_domain = sorted(detail_domains)[0] if detail_domains else ""
                    details[creative_id] = {
                        "target_domain": target_domain,
                        "format": self._infer_creative_format(link_text, f"{outer_html}\n{page_html}", creative_id=creative_id),
                    }
                finally:
                    await detail_page.close()
            except Exception:
                pass

        return details

    async def _scroll_to_load_all(self, max_pages=None):
        max_pages = max_pages or self.max_scroll_pages
        prev_height = 0
        for _ in range(max_pages):
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
                if adv_id in seen_ids:
                    continue
                seen_ids.add(adv_id)
                name = ""
                start = max(0, match.start() - 300)
                end = min(len(body), match.end() + 300)
                context = body[start:end]
                for pattern in [
                    rf'"{adv_id}"\s*,\s*"([^"]+)"',
                    rf'"([^"]+)"\s*,\s*"{adv_id}"',
                ]:
                    name_match = re.search(pattern, context)
                    if not name_match:
                        continue
                    candidate = name_match.group(1)
                    if len(candidate) < 100 and not candidate.startswith(("AR", "CR", "http")):
                        name = candidate
                        break
                advertisers.append(
                    AdvertiserInfo(
                        advertiser_id=adv_id,
                        name=name,
                        url=f"{self.BASE_URL}/advertiser/{adv_id}?region={self.region}",
                    )
                )
        return advertisers

    def _parse_domains_from_intercepted(self) -> set[str]:
        domains = set()
        for resp in self._intercepted_responses:
            domains.update(self._extract_contextual_domains(resp.get("body", "")))
        return domains

    def _parse_creatives_from_intercepted(self, advertiser_id: str) -> list[AdCreative]:
        creatives = []
        seen_ids = set()
        for resp in self._intercepted_responses:
            body = resp.get("body", "")
            for match in re.finditer(r'"(CR\d{15,25})"', body):
                cr_id = match.group(1)
                if cr_id in seen_ids:
                    continue
                seen_ids.add(cr_id)
                creatives.append(AdCreative(creative_id=cr_id, advertiser_id=advertiser_id))
        return creatives

    def _infer_creative_format(self, text: str, html_content: str, creative_id: str | None = None) -> str:
        haystack = f"{text}\n{html_content}".lower()
        if "videocam" in haystack or "youtube" in haystack or "hqdefault.jpg" in haystack:
            return "video"
        if "wide" in haystack:
            return "image_wide"
        if creative_id and re.search(rf"/creative/{re.escape(creative_id)}.*?grey-background(?![^>]*wide)", haystack, re.S):
            return "image"
        if "creative-bounding-box" in haystack:
            return "image"
        return ""

    async def search_domain(self, domain: str) -> ScrapeResult:
        normalized_query_domain = self._normalize_domain(domain) or domain.lower()
        result = ScrapeResult(query_domain=normalized_query_domain)
        search_url = f"{self.BASE_URL}/?region={self.region}&domain={quote(domain)}"
        self._intercepted_responses.clear()

        try:
            await self._page.goto(search_url, wait_until="domcontentloaded", timeout=self.timeout)
        except Exception:
            pass
        await asyncio.sleep(4)

        advertisers_from_api = self._parse_advertiser_from_intercepted()
        advertisers_from_dom = await self._extract_advertiser_from_dom()

        seen_ids = set()
        all_advertisers = []
        for advertiser in advertisers_from_api + advertisers_from_dom:
            if not advertiser.advertiser_id or advertiser.advertiser_id in seen_ids:
                continue
            seen_ids.add(advertiser.advertiser_id)
            all_advertisers.append(advertiser)

        if not all_advertisers:
            return result

        all_domains = set()
        all_creatives = []
        for advertiser in all_advertisers:
            advertiser_url = advertiser.url or (
                f"{self.BASE_URL}/advertiser/{advertiser.advertiser_id}?region={self.region}"
            )
            self._intercepted_responses.clear()
            try:
                await self._page.goto(advertiser_url, wait_until="domcontentloaded", timeout=self.timeout)
            except Exception:
                pass
            await asyncio.sleep(4)

            if not advertiser.name or advertiser.name == "Unknown":
                advertiser.name = await self._extract_advertiser_name_from_dom()

            await self._scroll_to_load_all()

            domains_from_api = self._parse_domains_from_intercepted()
            domains_from_dom = await self._extract_domains_from_dom()
            creative_details = await self._extract_creative_details_from_links(advertiser.advertiser_id)
            domains_from_creatives = {
                item["target_domain"]
                for item in creative_details.values()
                if item.get("target_domain")
            }

            advertiser_domains = domains_from_api | domains_from_dom | domains_from_creatives
            domain_sources = {
                candidate: sum(
                    candidate in source_domains
                    for source_domains in (
                        domains_from_api,
                        domains_from_dom,
                        domains_from_creatives,
                    )
                )
                for candidate in advertiser_domains
            }
            confident_domains = {
                candidate
                for candidate, source_count in domain_sources.items()
                if source_count >= 2
            }
            confident_domains.add(normalized_query_domain)

            advertiser.matched_domains = sorted(
                domain for domain in confident_domains if domain == normalized_query_domain
            )
            advertiser.other_domains = sorted(
                domain for domain in confident_domains if domain and domain != normalized_query_domain
            )
            advertiser.has_query_domain = normalized_query_domain in confident_domains
            all_domains.update(confident_domains)

            creatives_from_api = self._parse_creatives_from_intercepted(advertiser.advertiser_id)
            creatives_from_dom = await self._extract_creatives_from_dom(advertiser.advertiser_id)

            seen_creative_ids = {creative.creative_id for creative in all_creatives}
            for creative in creatives_from_api + creatives_from_dom:
                if creative.creative_id in seen_creative_ids:
                    continue
                seen_creative_ids.add(creative.creative_id)
                creative.advertiser_name = advertiser.name
                if creative.creative_id in creative_details:
                    detail = creative_details[creative.creative_id]
                    if detail.get("target_domain"):
                        creative.target_domain = detail["target_domain"]
                    if detail.get("format"):
                        creative.format = detail["format"]
                all_creatives.append(creative)

        all_domains.add(normalized_query_domain)
        result.advertisers = [asdict(advertiser) for advertiser in all_advertisers]
        result.all_domains = sorted(all_domains)
        result.other_domains = sorted(
            domain for domain in all_domains if domain != normalized_query_domain
        )
        result.ad_creatives = [asdict(creative) for creative in all_creatives]
        result.total_ads_found = len(all_creatives)
        result.has_ads = bool(all_advertisers or all_creatives)
        return result
