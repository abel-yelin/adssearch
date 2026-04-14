import random


def get_backoff_seconds(retry_count: int, base_delay: float = 3.0, max_delay: float = 60.0) -> float:
    delay = min(base_delay * (2 ** max(retry_count - 1, 0)), max_delay)
    return round(delay + random.uniform(0, 1.5), 2)


def get_jitter_delay_seconds(min_delay: float, max_delay: float) -> float:
    lower = min(min_delay, max_delay)
    upper = max(min_delay, max_delay)
    return round(random.uniform(lower, upper), 2)


def get_block_cooldown_seconds(retry_count: int, base_delay: float = 20.0, max_delay: float = 90.0) -> float:
    return get_backoff_seconds(retry_count, base_delay=base_delay, max_delay=max_delay)
