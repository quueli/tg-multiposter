from datetime import datetime, timedelta

import scheduler


def test_schedule_post_assigns_an_id():
    post = scheduler.schedule_post({"scheduled": []}, {"text": "x"}, send_at=datetime(2026, 2, 1, 10, 0))
    assert post["id"]
    assert post["text"] == "x"


def test_due_posts_returns_only_past_due():
    now = datetime(2026, 2, 1, 12, 0)
    scheduled = [
        {"id": "a", "send_at": (now - timedelta(minutes=1)).isoformat()},
        {"id": "b", "send_at": (now + timedelta(minutes=5)).isoformat()},
    ]
    due = scheduler.due_posts(scheduled, now)
    assert [p["id"] for p in due] == ["a"]
