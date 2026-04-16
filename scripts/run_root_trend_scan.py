import argparse
import json
from pathlib import Path

import httpx


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the free Google Trends root discovery scan.")
    parser.add_argument("--api-base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--keywords-file", required=True, help="Text file containing comma/newline separated roots.")
    parser.add_argument("--time-range", default="today 3-m")
    parser.add_argument("--geo", default="")
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=5)
    parser.add_argument("--batch-delay-seconds", type=float, default=2.0)
    args = parser.parse_args()

    keyword_blob = Path(args.keywords_file).read_text(encoding="utf-8")
    payload = {
        "keyword_blob": keyword_blob,
        "time_range": args.time_range,
        "geo": args.geo,
        "top_n": args.top_n,
        "batch_size": args.batch_size,
        "batch_delay_seconds": args.batch_delay_seconds,
    }

    with httpx.Client(timeout=120.0) as client:
        response = client.post(f"{args.api_base_url.rstrip('/')}/api/trends/root-discovery", json=payload)
        response.raise_for_status()
        print(json.dumps(response.json(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
