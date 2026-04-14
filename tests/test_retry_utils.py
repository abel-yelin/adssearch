from app.utils.retry import get_block_cooldown_seconds, get_jitter_delay_seconds


def test_jitter_delay_stays_within_range():
    value = get_jitter_delay_seconds(4, 9)
    assert 4 <= value <= 9


def test_block_cooldown_grows_with_retry_count():
    first = get_block_cooldown_seconds(1, base_delay=20, max_delay=90)
    second = get_block_cooldown_seconds(2, base_delay=20, max_delay=90)
    assert second >= first
