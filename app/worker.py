from rq import Connection, Worker
from redis import Redis

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import engine
from app.models import search_task  # noqa: F401
from app.core.logging import configure_logging, get_logger


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger = get_logger(__name__)
    redis = Redis.from_url(settings.redis_url)
    Base.metadata.create_all(bind=engine)
    logger.info(
        "Starting worker for queue=%s redis=%s",
        settings.queue_name,
        settings.redis_url,
    )
    with Connection(redis):
        worker = Worker([settings.queue_name])
        worker.work()


if __name__ == "__main__":
    main()
