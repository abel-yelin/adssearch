# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Google Ads Transparency Scraper API - A FastAPI application that scrapes Google's Ads Transparency Center to retrieve advertiser information, domains, and ad creatives for a given domain.

## Build Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Install Playwright browser (required first time)
playwright install chromium

# Run development server
uvicorn main:app --host 0.0.0.0 --port 8000

# Docker build and run
docker build -t ads-scraper-api .
docker run -p 8000:8000 ads-scraper-api
```

## Architecture

Single-file FastAPI application (`main.py`) with three logical layers:

### Data Models
- `AdvertiserInfo`: Advertiser ID, name, URL, region
- `AdCreative`: Creative ID, advertiser info, format, dates
- `ScrapeResult`: Query results container
- Pydantic `SearchRequest`/`SearchResponse` for API validation

### Core Scraper (`GoogleAdsTransparencyScraper`)
Uses Playwright for browser automation with dual data extraction:
1. **Network interception**: Captures `batchexecute` and `TransparencyReport` API responses
2. **DOM parsing**: Extracts advertiser links and domain patterns from rendered HTML

Key methods:
- `search_domain(domain)` - Main entry point, orchestrates scraping
- `_extract_advertiser_from_dom()` - Finds advertiser links via selectors/regex
- `_extract_domains_from_dom()` - Regex-based domain extraction from page text
- `_scroll_to_load_all()` - Infinite scroll pagination

### API Endpoints
- `GET /api/health` - Health check
- `POST /api/search` - Domain query (30s-3min execution time)

## API Request Parameters

```json
{
  "domain": "example.com",
  "region": "anywhere",
  "max_scroll_pages": 10,
  "proxy": null,
  "timeout": 30000
}
```

## Notes

- Queries are synchronous and can take 1-3 minutes
- CORS is configured to allow all origins
- No database - task storage is in-memory (production should use Redis)
