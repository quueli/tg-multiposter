import asyncio

import sender
from examples.fake_bot import DEAD_CHAT_ID, FakeBot


def test_multipost_counts_success_and_drops_dead_chats():
    bot = FakeBot()
    groups = [{"id": 1001}, {"id": DEAD_CHAT_ID}, {"id": 1002}]
    result = asyncio.run(sender.multipost(bot, groups, text="hello"))
    assert result["total"] == 3
    assert result["success"] == 2
    assert result["errors"] == 1
    assert result["removed_ids"] == [DEAD_CHAT_ID]


def test_media_group_only_first_item_keeps_caption():
    media = [
        {"type": "photo", "file_id": "a", "caption": "cap"},
        {"type": "photo", "file_id": "b", "caption": "cap"},
    ]
    built = sender.build_input_media(media)
    assert built[0].caption == "cap"
    assert built[1].caption is None
