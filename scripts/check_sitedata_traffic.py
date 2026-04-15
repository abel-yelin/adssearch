import argparse
import json
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


from app.collectors.sitedata_traffic_collector import SiteDataTrafficCollector, SiteDataTrafficCollectorError


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test the SiteData traffic collector.")
    parser.add_argument("--domain", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=30)
    parser.add_argument("--proxy", default=None)
    args = parser.parse_args()

    collector = SiteDataTrafficCollector(timeout_seconds=args.timeout_seconds, proxy=args.proxy)
    try:
        payload = collector.fetch(args.domain)
    except SiteDataTrafficCollectorError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "code": exc.code,
                    "message": exc.message,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2

    summary = {
        "ok": True,
        "requested_domain": payload.get("requested_domain"),
        "resolved_domain": payload.get("resolved_domain"),
        "site_name": payload.get("SiteName"),
        "snapshot_date": payload.get("SnapshotDate"),
        "monthly_points": len(payload.get("EstimatedMonthlyVisits") or {}),
        "top_keywords_count": len(payload.get("TopKeywords") or []),
        "top_country_count": len(payload.get("TopCountryShares") or []),
        "traffic_sources": payload.get("TrafficSources") or {},
        "engagments": payload.get("Engagments") or {},
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
