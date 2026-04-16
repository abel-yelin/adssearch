import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


from app.free_trends.config import load_config
from app.free_trends.service import build_live_service


def configure_logging(log_file: str) -> logging.Logger:
    logger = logging.getLogger("free_trends")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger


async def main_async(config_path: str) -> int:
    config = load_config(config_path)
    logger = configure_logging(config.log_file)
    service = build_live_service(config, logger=logger)
    await service.collector.start()
    try:
        summary = await service.run_once()
    finally:
        await service.collector.close()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the standalone free Google Trends discovery service once.")
    parser.add_argument("--config", required=True, help="Path to the JSON config file.")
    args = parser.parse_args()
    return asyncio.run(main_async(args.config))


if __name__ == "__main__":
    raise SystemExit(main())
