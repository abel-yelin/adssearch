from datetime import datetime
import time

from app.services.whois_service import WhoisService, parse_whois_data


class FakeWhoisClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def lookup(self, domain: str):
        self.calls.append(domain)
        result = self.responses[domain]
        if isinstance(result, Exception):
            raise result
        return result


def test_parse_whois_data_marks_available_from_indicator_text():
    result = parse_whois_data({"raw": "No match for domain EXAMPLE.COM"}, "example.com")
    assert result.available is True
    assert result.error is False


def test_parse_whois_data_extracts_registered_domain_fields():
    result = parse_whois_data(
        {
            "registrar": "Namecheap",
            "creation_date": datetime(2021, 5, 1, 12, 0, 0),
            "expiration_date": datetime(2027, 5, 1, 12, 0, 0),
        },
        "voyagehub.com",
    )

    assert result.available is False
    assert result.error is False
    assert result.registrar == "Namecheap"
    assert result.created_date.startswith("2021-05-01T12:00:00")
    assert result.expires_date.startswith("2027-05-01T12:00:00")


def test_whois_service_caches_successful_results():
    client = FakeWhoisClient({"example.com": {"raw": "No match for domain EXAMPLE.COM"}})
    current_time = [1000.0]
    service = WhoisService(
        lookup_client=client,
        time_fn=lambda: current_time[0],
    )

    first = service.check_domains(["example.com"])
    second = service.check_domains(["example.com"])

    assert first[0].available is True
    assert second[0].available is True
    assert client.calls == ["example.com"]


def test_whois_service_returns_error_for_unparseable_failures():
    client = FakeWhoisClient({"broken.com": RuntimeError("network down")})
    service = WhoisService(lookup_client=client)

    results = service.check_domains(["broken.com"])

    assert results[0].domain == "broken.com"
    assert results[0].available is False
    assert results[0].error is True


def test_whois_service_timeout_does_not_block_until_lookup_finishes():
    class SlowWhoisClient:
        def lookup(self, domain: str):
            time.sleep(0.2)
            return {"registrar": "Too Slow"}

    service = WhoisService(lookup_client=SlowWhoisClient())
    service.timeout_seconds = 0.01

    start = time.monotonic()
    results = service.check_domains(["slow.com"])
    elapsed = time.monotonic() - start

    assert elapsed < 0.15
    assert results[0].domain == "slow.com"
    assert results[0].error is True
