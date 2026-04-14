import asyncio

from rq import get_current_job

from app.collectors.trends_collector import GoogleTrendsCollector, TrendsCollectorError
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.session import get_db_session
from app.repositories.trend_task_repository import TrendTaskRepository
from app.schemas.task import TrendTaskCreateRequest
from app.services.keyword_service import KeywordService
from app.services.queue_service import TaskQueueService
from app.utils.keyword_filters import normalize_keyword
from app.utils.retry import get_backoff_seconds, get_block_cooldown_seconds, get_jitter_delay_seconds


logger = get_logger(__name__)


def run_trend_task(payload: dict) -> dict:
    settings = get_settings()
    configure_logging(settings.log_level)
    request = TrendTaskCreateRequest(**payload)
    job = get_current_job()
    task_id = job.id if job else None
    if task_id is None:
        raise RuntimeError("Trend task must be executed inside an RQ job.")

    result = asyncio.run(_run_trend_task(task_id, request))
    return result


async def _run_trend_task(task_id: str, request: TrendTaskCreateRequest) -> dict:
    settings = get_settings()
    resolved_proxy = request.proxy or settings.trend_default_proxy
    collector = GoogleTrendsCollector(proxy=resolved_proxy, language=request.language)
    keyword_service = KeywordService()
    queue_service = TaskQueueService(settings)

    with get_db_session() as session:
        TrendTaskRepository(session).set_task_status(task_id, "running", started=True)
    queue_service.set_progress(task_id, {"status": "running", "current_batch_no": 0})

    await collector.start()
    try:
        while True:
            with get_db_session() as session:
                repo = TrendTaskRepository(session)
                task = repo.get_task(task_id)
                if task is None:
                    raise RuntimeError(f"Task {task_id} no longer exists.")
                if task.status == "cancelled":
                    result = _build_result(repo, task_id, "cancelled")
                    repo.set_task_status(task_id, "cancelled", result_payload=result, finished=True)
                    queue_service.set_progress(task_id, result)
                    return result
                if task.processed_keywords_count >= task.max_keywords:
                    result = _build_result(repo, task_id, "completed")
                    repo.set_task_status(task_id, "completed", result_payload=result, finished=True)
                    queue_service.set_progress(task_id, result)
                    return result

                next_keywords = repo.pick_next_keywords(task_id, limit=4)
                if not next_keywords:
                    repo.refresh_task_counters(task_id)
                    result = _build_result(repo, task_id, "completed")
                    repo.set_task_status(task_id, "completed", result_payload=result, finished=True)
                    queue_service.set_progress(task_id, result)
                    return result

                batch_no = task.current_batch_no + 1
                batch_keywords = [row.keyword for row in next_keywords]
                batch = repo.create_batch(task_id, batch_no, batch_keywords)
                repo.refresh_task_counters(task_id)
                queue_service.set_progress(
                    task_id,
                    {
                        "status": "running",
                        "current_batch_no": batch_no,
                        "current_keywords": batch_keywords,
                        "processed_keywords_count": task.processed_keywords_count,
                        "effective_keywords_count": task.effective_keywords_count,
                    },
                )

            retry_count = 0
            capture_result = None
            while retry_count < 3:
                try:
                    if retry_count == 0:
                        await _sleep_before_batch(
                            queue_service=queue_service,
                            task_id=task_id,
                            batch_no=batch_no,
                            min_seconds=settings.trend_batch_delay_min_seconds,
                            max_seconds=settings.trend_batch_delay_max_seconds,
                        )
                    capture_result = await collector.capture(
                        base_keyword=request.base_keyword,
                        keywords=batch_keywords,
                        time_range=request.time_range,
                        geo=request.geo,
                        timezone_offset=request.timezone_offset,
                    )
                    break
                except TrendsCollectorError as exc:
                    retry_count += 1
                    retry_status = "cooldown" if exc.code == "captcha_or_blocked" and retry_count < 3 else "retrying"
                    with get_db_session() as session:
                        repo = TrendTaskRepository(session)
                        repo.update_batch_status(
                            batch.id,
                            retry_status if retry_count < 3 else "failed",
                            retry_count=retry_count,
                            error_code=exc.code,
                            error_message=exc.message,
                        )
                        repo.set_task_status(
                            task_id,
                            retry_status if retry_count < 3 else "failed",
                            error_code=exc.code,
                            error_message=exc.message,
                            increment_retry=True,
                            finished=retry_count >= 3,
                        )
                        if retry_count >= 3:
                            repo.revert_keywords_to_queue(task_id, batch_keywords)
                            result = _build_result(repo, task_id, "failed")
                            repo.set_task_status(task_id, "failed", error_code=exc.code, error_message=exc.message, result_payload=result, finished=True)
                            queue_service.set_progress(task_id, result)
                            return result
                    delay_seconds = (
                        get_block_cooldown_seconds(
                            retry_count,
                            base_delay=settings.trend_block_cooldown_base_seconds,
                            max_delay=settings.trend_block_cooldown_max_seconds,
                        )
                        if exc.code == "captcha_or_blocked"
                        else get_backoff_seconds(retry_count)
                    )
                    queue_service.set_progress(
                        task_id,
                        {
                            "status": retry_status if retry_count < 3 else "failed",
                            "current_batch_no": batch_no,
                            "current_keywords": batch_keywords,
                            "retry_count": retry_count,
                            "retry_in_seconds": delay_seconds,
                            "error_code": exc.code,
                            "error_message": exc.message,
                            "proxy": resolved_proxy,
                        },
                    )
                    await asyncio.sleep(delay_seconds)

            if capture_result is None:
                raise RuntimeError("Capture result missing after retry loop.")

            with get_db_session() as session:
                repo = TrendTaskRepository(session)
                repo.save_payload(batch.id, "related_queries", {"items": capture_result["related_queries"]})
                repo.save_payload(batch.id, "multiline_data", capture_result["multiline_data"] or {})
                repo.save_payload(batch.id, "raw_requests", {"items": capture_result["raw_requests"]})

                related_candidates = keyword_service.extract_related_keywords(capture_result["related_queries"])
                for candidate, source_keyword in related_candidates:
                    skip_reason = keyword_service.validate_candidate(candidate, request.base_keyword)
                    status = "skipped" if skip_reason else "queued"
                    repo.add_keyword(
                        task_id=task_id,
                        keyword=normalize_keyword(candidate),
                        source_keyword=source_keyword,
                        source_type="related",
                        status=status,
                        skip_reason=skip_reason,
                    )

                effective_keywords = keyword_service.evaluate_effective_keywords(
                    base_keyword=request.base_keyword,
                    candidate_keywords=batch_keywords,
                    multiline_payload=capture_result["multiline_data"],
                    threshold=request.threshold,
                )
                for item in effective_keywords:
                    repo.add_effective_keyword(task_id, batch.id, item["keyword"], item)

                repo.mark_keywords_processed(task_id, batch_keywords)
                repo.update_batch_status(batch.id, "succeeded", retry_count=retry_count, finished=True)
                repo.refresh_task_counters(task_id)
                latest_task = repo.get_task(task_id)
                if latest_task and latest_task.processed_keywords_count >= latest_task.max_keywords:
                    result = _build_result(repo, task_id, "completed")
                    repo.set_task_status(task_id, "completed", result_payload=result, finished=True)
                    queue_service.set_progress(task_id, result)
                    return result
                repo.set_task_status(task_id, "running")
                queue_service.set_progress(task_id, _build_result(repo, task_id, "running"))
    except Exception as exc:
        logger.exception("Trend task failed: task_id=%s", task_id)
        with get_db_session() as session:
            repo = TrendTaskRepository(session)
            result = _build_result(repo, task_id, "failed")
            repo.set_task_status(
                task_id,
                "failed",
                error_code="internal_error",
                error_message=str(exc),
                result_payload=result,
                finished=True,
            )
            queue_service.set_progress(task_id, result)
            return result
    finally:
        await collector.close()


def _build_result(repo: TrendTaskRepository, task_id: str, status: str) -> dict:
    task = repo.refresh_task_counters(task_id) or repo.get_task(task_id)
    effective_keywords = repo.list_effective_keywords(task_id, limit=20)
    return {
        "task_id": task_id,
        "status": status,
        "processed_keywords_count": task.processed_keywords_count if task else 0,
        "effective_keywords_count": task.effective_keywords_count if task else 0,
        "current_batch_no": task.current_batch_no if task else 0,
        "effective_keywords_sample": [
            {"keyword": item.keyword, "score_percent": float(item.score_percent)}
            for item in effective_keywords
        ],
    }


async def _sleep_before_batch(
    *,
    queue_service: TaskQueueService,
    task_id: str,
    batch_no: int,
    min_seconds: float,
    max_seconds: float,
) -> None:
    delay_seconds = get_jitter_delay_seconds(min_seconds, max_seconds)
    queue_service.set_progress(
        task_id,
        {
            "status": "cooldown",
            "current_batch_no": batch_no,
            "retry_in_seconds": delay_seconds,
            "message": "Waiting before the next Google Trends batch to reduce rate-limit risk.",
        },
    )
    await asyncio.sleep(delay_seconds)
