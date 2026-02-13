from types import SimpleNamespace

from aiogram.exceptions import TelegramForbiddenError

DEAD_CHAT_ID = 3001    # bot was removed from this one


class FakeBot:
    def __init__(self):
        self.calls = []
        self._next_message_id = 1

    def _message(self, chat_id):
        msg = SimpleNamespace(message_id=self._next_message_id, chat=SimpleNamespace(id=chat_id))
        self._next_message_id += 1
        return msg

    async def _send(self, kind, chat_id, **kwargs):
        self.calls.append((kind, chat_id, kwargs))

        if chat_id == DEAD_CHAT_ID:
            raise TelegramForbiddenError(method=None, message="bot was kicked from the chat")

        return self._message(chat_id)

    async def send_message(self, chat_id, text, entities=None, **kwargs):
        return await self._send("message", chat_id, text=text, entities=entities)

    async def send_photo(self, chat_id, photo, caption=None, caption_entities=None, **kwargs):
        return await self._send("photo", chat_id, photo=photo, caption=caption)

    async def send_video(self, chat_id, video, caption=None, caption_entities=None, **kwargs):
        return await self._send("video", chat_id, video=video, caption=caption)

    async def send_document(self, chat_id, document, caption=None, caption_entities=None, **kwargs):
        return await self._send("document", chat_id, document=document, caption=caption)

    async def send_audio(self, chat_id, audio, caption=None, caption_entities=None, **kwargs):
        return await self._send("audio", chat_id, audio=audio, caption=caption)

    async def send_voice(self, chat_id, voice, caption=None, caption_entities=None, **kwargs):
        return await self._send("voice", chat_id, voice=voice, caption=caption)

    async def send_video_note(self, chat_id, video_note, **kwargs):
        return await self._send("video_note", chat_id, video_note=video_note)

    async def send_sticker(self, chat_id, sticker, **kwargs):
        return await self._send("sticker", chat_id, sticker=sticker)

    async def send_media_group(self, chat_id, media, **kwargs):
        await self._send("media_group", chat_id, count=len(media))
        return [self._message(chat_id) for _ in media]

    async def pin_chat_message(self, chat_id, message_id, disable_notification=False, **kwargs):
        return await self._send("pin", chat_id, message_id=message_id)

    async def get_me(self):
        return SimpleNamespace(username="example_multipost_bot", first_name="Example Multiposter")
