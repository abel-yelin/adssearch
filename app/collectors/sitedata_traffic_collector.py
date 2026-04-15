import hashlib
import json
import random
import subprocess
import time
from typing import Any
from urllib.parse import urlparse


class SiteDataTrafficCollectorError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class SiteDataTrafficCollector:
    BASE_URL = "https://traffic.sitedata.dev/"
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36"
    )
    SIGN_SALT = "2@3&^8d4$%H9,M"

    def __init__(self, timeout_seconds: int = 30, proxy: str | None = None):
        self.timeout_seconds = timeout_seconds
        self.proxy = proxy

    def fetch(self, domain: str) -> dict[str, Any]:
        normalized_domain = self._normalize_domain(domain)
        errors: list[SiteDataTrafficCollectorError] = []

        for candidate_domain in self._candidate_domains(normalized_domain):
            try:
                payload = self._request_once(candidate_domain)
                payload["requested_domain"] = normalized_domain
                payload["resolved_domain"] = candidate_domain
                return payload
            except SiteDataTrafficCollectorError as exc:
                errors.append(exc)
                if exc.code not in {"unauthorized_client", "service_rate_limited"}:
                    raise

        if errors:
            raise errors[-1]
        raise SiteDataTrafficCollectorError("unknown_error", "SiteData request failed without a specific error.")

    def _request_once(self, domain: str) -> dict[str, Any]:
        params = self._build_signed_params(domain)
        command = [
            "curl",
            "-sS",
            "-L",
            "--max-time",
            str(self.timeout_seconds),
            "--request",
            "GET",
            "--url",
            self.BASE_URL,
            "--get",
            "-H",
            "Accept: application/json",
            "-H",
            f"Origin: https://sitedata.dev",
            "-H",
            f"Referer: https://sitedata.dev/traffic/{domain}",
            "-A",
            self.USER_AGENT,
        ]
        if self.proxy:
            command.extend(["--proxy", self.proxy])
        for key, value in params.items():
            command.extend(["--data-urlencode", f"{key}={value}"])
        command.extend(["-w", "\n__STATUS__:%{http_code}"])

        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0 and "__STATUS__:" not in result.stdout:
            message = result.stderr.strip() or result.stdout.strip() or "curl request failed"
            raise SiteDataTrafficCollectorError("transport_error", f"SiteData request failed: {message}")

        body, status_code = self._parse_curl_output(result.stdout)
        try:
            payload = json.loads(body) if body else {}
        except json.JSONDecodeError as exc:
            raise SiteDataTrafficCollectorError("invalid_response", "SiteData returned non-JSON content.") from exc

        if status_code == 200 and isinstance(payload, dict) and not payload.get("error"):
            return payload

        error_message = str(payload.get("error") or f"HTTP {status_code}")
        lowered = error_message.lower()
        if status_code == 429 or "unauthorized clientid" in lowered:
            raise SiteDataTrafficCollectorError("unauthorized_client", error_message)
        if status_code in {401, 403}:
            raise SiteDataTrafficCollectorError("access_denied", error_message)
        if status_code >= 500:
            raise SiteDataTrafficCollectorError("upstream_error", error_message)
        raise SiteDataTrafficCollectorError("invalid_request", error_message)

    def _build_signed_params(self, domain: str) -> dict[str, str]:
        client_id = self._generate_client_id()
        timestamp = str(int(time.time() * 1000))
        sign = hashlib.sha256(f"{client_id}{timestamp}{self.SIGN_SALT}".encode()).hexdigest()[:32]
        return {
            "domain": domain,
            "source": "web",
            "clientId": client_id,
            "timestamp": timestamp,
            "sign": sign,
        }

    @staticmethod
    def _parse_curl_output(stdout: str) -> tuple[str, int]:
        marker = "\n__STATUS__:"
        if marker not in stdout:
            raise SiteDataTrafficCollectorError("transport_error", "curl output did not include HTTP status marker.")
        body, status_raw = stdout.rsplit(marker, 1)
        try:
            status_code = int(status_raw.strip())
        except ValueError as exc:
            raise SiteDataTrafficCollectorError("transport_error", "curl output contained an invalid HTTP status.") from exc
        return body.strip(), status_code

    @staticmethod
    def _generate_client_id() -> str:
        alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"
        suffix = "".join(random.choice(alphabet) for _ in range(12))
        return f"anon_{int(time.time() * 1000)}_{suffix}"

    @staticmethod
    def _normalize_domain(raw_domain: str) -> str:
        value = (raw_domain or "").strip().lower()
        if not value:
            raise SiteDataTrafficCollectorError("invalid_domain", "A domain is required.")

        if "://" not in value:
            value = f"https://{value}"
        parsed = urlparse(value)
        host = (parsed.netloc or parsed.path).strip().lower()
        host = host.split("/", 1)[0].split(":", 1)[0]
        if not host or "." not in host:
            raise SiteDataTrafficCollectorError("invalid_domain", f"Invalid domain '{raw_domain}'.")
        return host

    @staticmethod
    def _candidate_domains(domain: str) -> list[str]:
        candidates = [domain]
        if domain.startswith("www."):
            candidates.append(domain[4:])
        return list(dict.fromkeys(candidates))
