import gzip
import hashlib
from datetime import UTC, datetime
from io import BytesIO
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree as ET

import httpx


class SitemapFetcherError(RuntimeError):
    pass


class SitemapFetcher:
    def __init__(
        self,
        *,
        timeout_seconds: int = 30,
        max_files: int = 2000,
        user_agent: str = "adssearch-sitemap-monitor/1.0",
        client: httpx.Client | None = None,
    ):
        self.timeout_seconds = timeout_seconds
        self.max_files = max_files
        self.user_agent = user_agent
        self._client = client

    def discover_sitemap_url(self, site_url: str) -> str:
        parsed = urlparse(site_url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        candidates = [
            urljoin(origin, "/sitemap.xml"),
            urljoin(origin, "/sitemap_index.xml"),
        ]
        with self._get_client() as client:
            for candidate in candidates:
                response = client.get(candidate)
                if response.status_code == 200:
                    return str(response.url)
        return candidates[0]

    def fetch_snapshot(self, sitemap_url: str, previous_snapshot: dict | None = None) -> tuple[dict, dict]:
        previous_files = (previous_snapshot or {}).get("files", {})
        state = {
            "files": {},
            "url_entries": {},
            "visited": set(),
            "stats": {
                "downloaded_files": 0,
                "reused_files": 0,
                "changed_files": 0,
                "unchanged_by_hash_files": 0,
            },
        }

        with self._get_client() as client:
            self._crawl(client, sitemap_url, previous_files, state)

        snapshot = {
            "root_url": sitemap_url,
            "fetched_at": datetime.now(UTC).isoformat(),
            "files": state["files"],
            "url_entries": state["url_entries"],
            "stats": {
                **state["stats"],
                "file_count": len(state["files"]),
                "url_count": len(state["url_entries"]),
            },
        }
        return snapshot, snapshot["stats"]

    def _crawl(self, client: httpx.Client, sitemap_url: str, previous_files: dict, state: dict) -> None:
        if sitemap_url in state["visited"]:
            return
        if len(state["visited"]) >= self.max_files:
            raise SitemapFetcherError(f"Exceeded max sitemap file limit: {self.max_files}")
        state["visited"].add(sitemap_url)

        previous_file = previous_files.get(sitemap_url)
        record = self._fetch_one(client, sitemap_url, previous_file, state)
        state["files"][sitemap_url] = record

        if record["file_type"] == "urlset":
            for entry in record["urls"]:
                state["url_entries"][entry["loc"]] = {
                    "lastmod": entry.get("lastmod"),
                    "source_sitemap": sitemap_url,
                }
            return

        for child in record["children"]:
            self._crawl(client, child["loc"], previous_files, state)

    def _fetch_one(self, client: httpx.Client, sitemap_url: str, previous_file: dict | None, state: dict) -> dict:
        headers = {"User-Agent": self.user_agent}
        if previous_file:
            if previous_file.get("etag"):
                headers["If-None-Match"] = previous_file["etag"]
            if previous_file.get("last_modified"):
                headers["If-Modified-Since"] = previous_file["last_modified"]

        response = client.get(sitemap_url, headers=headers)
        if response.status_code == 304 and previous_file is not None:
            state["stats"]["reused_files"] += 1
            return previous_file
        if response.status_code >= 400:
            raise SitemapFetcherError(f"Failed to fetch sitemap {sitemap_url}: HTTP {response.status_code}")

        content = self._decode_content(response, sitemap_url)
        parsed = self._parse_xml(content, sitemap_url)
        content_hash = hashlib.sha256(content).hexdigest()

        state["stats"]["downloaded_files"] += 1
        if previous_file and previous_file.get("content_hash") == content_hash:
            state["stats"]["unchanged_by_hash_files"] += 1
        else:
            state["stats"]["changed_files"] += 1

        record = {
            "url": sitemap_url,
            "file_type": parsed["file_type"],
            "etag": response.headers.get("etag"),
            "last_modified": response.headers.get("last-modified"),
            "content_hash": content_hash,
            "urls": parsed.get("urls", []),
            "children": parsed.get("children", []),
        }
        return record

    def _decode_content(self, response: httpx.Response, sitemap_url: str) -> bytes:
        content = response.content
        content_type = response.headers.get("content-type", "").lower()
        is_gzip = sitemap_url.endswith(".gz") or "gzip" in content_type or content[:2] == b"\x1f\x8b"
        if not is_gzip:
            return content
        try:
            return gzip.GzipFile(fileobj=BytesIO(content)).read()
        except OSError as exc:
            raise SitemapFetcherError(f"Invalid gzip sitemap: {sitemap_url}") from exc

    def _parse_xml(self, content: bytes, base_url: str) -> dict:
        try:
            root = ET.fromstring(content)
        except ET.ParseError as exc:
            raise SitemapFetcherError(f"Invalid XML in sitemap {base_url}") from exc

        root_name = self._local_name(root.tag)
        if root_name == "sitemapindex":
            return {
                "file_type": "sitemap_index",
                "children": [
                    {
                        "loc": self._normalize_location(self._get_child_text(item, "loc"), base_url),
                        "lastmod": self._get_child_text(item, "lastmod"),
                    }
                    for item in root
                    if self._local_name(item.tag) == "sitemap" and self._get_child_text(item, "loc")
                ],
            }
        if root_name == "urlset":
            return {
                "file_type": "urlset",
                "urls": [
                    {
                        "loc": self._normalize_location(self._get_child_text(item, "loc"), base_url),
                        "lastmod": self._get_child_text(item, "lastmod"),
                    }
                    for item in root
                    if self._local_name(item.tag) == "url" and self._get_child_text(item, "loc")
                ],
            }
        raise SitemapFetcherError(f"Unsupported sitemap root '{root_name}' in {base_url}")

    def _get_child_text(self, node: ET.Element, name: str) -> str | None:
        for child in node:
            if self._local_name(child.tag) == name:
                return (child.text or "").strip() or None
        return None

    def _normalize_location(self, value: str | None, base_url: str) -> str:
        if not value:
            return ""
        return urljoin(base_url, value.strip())

    def _local_name(self, value: str) -> str:
        return value.split("}", 1)[-1].lower()

    def _get_client(self):
        if self._client is not None:
            return _ClientContext(self._client)
        return httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={"Accept": "application/xml,text/xml;q=0.9,*/*;q=0.1"},
        )


class _ClientContext:
    def __init__(self, client: httpx.Client):
        self.client = client

    def __enter__(self) -> httpx.Client:
        return self.client

    def __exit__(self, exc_type, exc, tb) -> None:
        return None
