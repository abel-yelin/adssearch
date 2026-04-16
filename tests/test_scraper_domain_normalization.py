import asyncio
from unittest.mock import AsyncMock, Mock

from app.services.scraper import GoogleAdsTransparencyScraper


def test_search_domain_uses_normalized_domain_in_google_ads_query(monkeypatch):
    scraper = GoogleAdsTransparencyScraper()
    scraper._page = Mock()
    scraper._page.goto = AsyncMock()
    monkeypatch.setattr("app.services.scraper.asyncio.sleep", AsyncMock())

    scraper._extract_advertiser_from_dom = AsyncMock(return_value=[])
    monkeypatch.setattr(scraper, "_parse_advertiser_from_intercepted", lambda: [])

    asyncio.run(scraper.search_domain("https://www.pdftobrainrot.org/"))

    called_url = scraper._page.goto.await_args.args[0]
    assert "domain=pdftobrainrot.org" in called_url
    assert "https%3A" not in called_url
