import argparse
import asyncio
import json
import logging
import signal
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


from app.free_trends.config import load_config
from app.free_trends.scheduler import build_scheduler
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

    loop = asyncio.get_running_loop()

    async def run_job():
        await service.run_once()

    def run_job_sync():
        asyncio.run(run_job())

    scheduler = build_scheduler(config, run_job_sync)
    scheduler.start()
    logger.info("free trends scheduler started next_jobs=%s", scheduler.get_jobs())
    Path(config.status_file).write_text(
        json.dumps({"status": "idle", "schedule_time": config.schedule_time}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    stop_event = asyncio.Event()

    def _stop(*_args):
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _stop)
        except NotImplementedError:
            signal.signal(sig, lambda *_args: stop_event.set())

    try:
        await stop_event.wait()
    finally:
        scheduler.shutdown(wait=False)
        await service.collector.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the standalone free Google Trends discovery daemon.")
    parser.add_argument("--config", required=True, help="Path to the JSON config file.")
    args = parser.parse_args()
    return asyncio.run(main_async(args.config))


if __name__ == "__main__":
    raise SystemExit(main())
