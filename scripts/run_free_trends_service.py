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
    run_lock = asyncio.Lock()

    async def execute_run(*, request_id: str | None = None):
        async with run_lock:
            if request_id:
                await service.run_once_for_request(request_id)
            else:
                await service.run_once()

    async def run_job():
        await execute_run()

    def run_job_sync():
        asyncio.run(run_job())

    async def poll_run_requests() -> None:
        while not stop_event.is_set():
            claimed = service.storage.claim_next_pending_run_request(utcnow())
            if claimed is not None:
                request_id = claimed["request_id"]
                logger.info("free trends picked pending request request_id=%s", request_id)
                try:
                    await execute_run(request_id=request_id)
                except Exception as exc:
                    logger.exception("free trends request execution failed request_id=%s", request_id)
                    service.storage.finish_run_request(
                        request_id,
                        status="failed",
                        finished_at=utcnow(),
                        error_message=str(exc),
                    )
            await asyncio.sleep(max(1, config.request_poll_seconds))

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

    poller_task = asyncio.create_task(poll_run_requests())

    try:
        await stop_event.wait()
    finally:
        poller_task.cancel()
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
