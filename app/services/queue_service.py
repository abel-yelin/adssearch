import json

from rq.command import send_stop_job_command
from redis import Redis
from rq import Queue
from rq.job import Job

from app.core.config import AppSettings


class TaskQueueService:
    def __init__(self, settings: AppSettings):
        self.settings = settings
        self._redis = Redis.from_url(settings.redis_url)
        self._queue = Queue(
            name=settings.queue_name,
            connection=self._redis,
            default_timeout=settings.queue_job_timeout,
        )

    @property
    def queue(self) -> Queue:
        return self._queue

    @property
    def redis(self) -> Redis:
        return self._redis

    def enqueue(self, func_path: str, payload: dict, job_id: str) -> Job:
        return self._queue.enqueue(
            func_path,
            payload,
            job_id=job_id,
            result_ttl=self.settings.queue_result_ttl,
            failure_ttl=self.settings.queue_failure_ttl,
            job_timeout=self.settings.queue_job_timeout,
            meta={
                "payload": payload,
                "retry_count": self.settings.queue_default_retry_count,
            },
        )

    def fetch_job(self, job_id: str) -> Job | None:
        return self._queue.fetch_job(job_id)

    def stop_job(self, job_id: str) -> None:
        send_stop_job_command(self._redis, job_id)

    def set_progress(self, task_id: str, payload: dict) -> None:
        self._redis.set(
            f"trend:task:{task_id}:progress",
            json.dumps(payload, ensure_ascii=False),
            ex=self.settings.queue_result_ttl,
        )

    def delete_progress(self, task_id: str) -> None:
        self._redis.delete(f"trend:task:{task_id}:progress")
