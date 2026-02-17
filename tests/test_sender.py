import pytest

import sender
from examples.fake_bot import DEAD_CHAT_ID, FLOOD_CHAT_ID, FakeBot


@pytest.fixture(autouse=True)
def _fast_flood(monkeypatch):
    # keep the retry path but don't actually sleep out the flood wait
    async def no_sleep(_seconds):
        return None
    monkeypatch.setattr(sender.asyncio, "sleep", no_sleep)


def test_multipost_counts_success_and_drops_dead_chats():
    bot = FakeBot()
    groups = [{"id": 1001}, {"id": FLOOD_CHAT_ID}, {"id": DEAD_CHAT_ID}, {"id": 1002}]
    import asyncio
    result = asyncio.run(sender.multipost(bot, groups, text="hello"))
    assert result["total"] == 4
    assert result["success"] == 3          # flood chat succeeds on retry
    assert result["errors"] == 1           # the dead chat
    assert result["removed_ids"] == [DEAD_CHAT_ID]


def test_flood_is_retried_not_dropped():
    bot = FakeBot()
    import asyncio
    result = asyncio.run(sender.multipost(bot, [{"id": FLOOD_CHAT_ID}], text="hi"))
    assert result["success"] == 1
    assert FLOOD_CHAT_ID not in result["removed_ids"]


def test_media_group_only_first_item_keeps_caption():
    media = [
        {"type": "photo", "file_id": "a", "caption": "cap"},
        {"type": "photo", "file_id": "b", "caption": "cap"},
    ]
    built = sender.build_input_media(media)
    assert built[0].caption == "cap"
    assert built[1].caption is None
