import random


def get_backoff_seconds(retry_count: int, base_delay: float = 3.0, max_delay: float = 60.0) -> float:
    delay = min(base_delay * (2 ** max(retry_count - 1, 0)), max_delay)
    return round(delay + random.uniform(0, 1.5), 2)

