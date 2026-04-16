from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.free_trends.config import FreeTrendsConfig


def build_scheduler(config: FreeTrendsConfig, run_callable) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=config.timezone)
    trigger = CronTrigger(
        hour=config.schedule_hour,
        minute=config.schedule_minute,
        timezone=config.timezone,
    )
    scheduler.add_job(run_callable, trigger=trigger, id="free-trends-daily-run", replace_existing=True)
    return scheduler
