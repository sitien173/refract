"""The e2e fixture seeds the old job's attempt outside the 7 day Insights window."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from refract.store import attempts
from tests.e2e.serve_seeded import seed


def test_old_seed_attempt_counts_only_in_the_30_day_window(tmp_path) -> None:
    seed(tmp_path)
    connection = sqlite3.connect(tmp_path / "refract.db")
    connection.row_factory = sqlite3.Row
    now = datetime.now(timezone.utc)
    in_7_days = attempts.counts_by_reason(connection, (now - timedelta(days=7)).isoformat())
    in_30_days = attempts.counts_by_reason(connection, (now - timedelta(days=30)).isoformat())
    assert in_7_days == {"initial": 101}
    assert in_30_days == {"initial": 102}
