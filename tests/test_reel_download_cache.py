from datetime import UTC, datetime

from src.reels.builder import mp4_url_is_live


def test_signed_mp4_cache_refreshes_after_provider_expiry() -> None:
    url = (
        "https://storage.example/reel.mp4?"
        "X-Goog-Date=20260818T090000Z&X-Goog-Expires=18000"
    )
    assert mp4_url_is_live(url, now=datetime(2026, 8, 18, 10, 0, tzinfo=UTC))
    assert not mp4_url_is_live(url, now=datetime(2026, 8, 18, 14, 59, tzinfo=UTC))


def test_durable_mp4_url_can_remain_cached() -> None:
    assert mp4_url_is_live("https://cdn.example/reel.mp4")
    assert not mp4_url_is_live(None)
