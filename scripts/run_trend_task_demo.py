import argparse
import json
import time

import httpx


def main() -> int:
    parser = argparse.ArgumentParser(description="Submit a Google Trends task and poll its progress.")
    parser.add_argument("--api-base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--base-keyword", default="openai")
    parser.add_argument("--seed-keywords", nargs="+", default=["chatgpt", "gpt-4"])
    parser.add_argument("--time-range", default="today 12-m")
    parser.add_argument("--threshold", type=int, default=20)
    parser.add_argument("--max-keywords", type=int, default=100)
    parser.add_argument("--geo", default="")
    parser.add_argument("--language", default="en-US")
    parser.add_argument("--timezone-offset", type=int, default=0)
    parser.add_argument("--proxy", default=None)
    parser.add_argument("--poll-interval", type=float, default=3.0)
    parser.add_argument("--max-polls", type=int, default=40)
    args = parser.parse_args()

    payload = {
        "base_keyword": args.base_keyword,
        "seed_keywords": args.seed_keywords,
        "time_range": args.time_range,
        "threshold": args.threshold,
        "max_keywords": args.max_keywords,
        "geo": args.geo,
        "language": args.language,
        "timezone_offset": args.timezone_offset,
        "proxy": args.proxy,
    }
    base = args.api_base_url.rstrip("/")

    with httpx.Client(timeout=30.0) as client:
        create_response = client.post(f"{base}/api/trends/tasks", json=payload)
        create_response.raise_for_status()
        created = create_response.json()
        task_id = created["task_id"]
        print(json.dumps({"created": created}, ensure_ascii=False, indent=2))

        for _ in range(args.max_polls):
            status_response = client.get(f"{base}/api/trends/tasks/{task_id}")
            status_response.raise_for_status()
            status_payload = status_response.json()
            print(json.dumps({"status": status_payload}, ensure_ascii=False, indent=2))

            if status_payload["status"] in {"completed", "failed", "cancelled"}:
                summary_response = client.get(f"{base}/api/trends/tasks/{task_id}/summary")
                summary_response.raise_for_status()
                export_response = client.get(f"{base}/api/trends/tasks/{task_id}/export")
                export_response.raise_for_status()
                print(json.dumps({"summary": summary_response.json()}, ensure_ascii=False, indent=2))
                print(json.dumps({"export": export_response.json()}, ensure_ascii=False, indent=2))
                return 0

            time.sleep(args.poll_interval)

    print(json.dumps({"error": "Task did not finish before max polls were exhausted."}, ensure_ascii=False, indent=2))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
