import asyncio
import logging
from random import uniform
from typing import Awaitable, Callable, Dict, List, Optional

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import InputMediaAudio, InputMediaDocument, InputMediaPhoto, InputMediaVideo

logger = logging.getLogger(__name__)

BASE_DELAY = 0.05
MAX_RETRIES = 3


def build_input_media(media_list: List[Dict]):
    # only the first item can carry a caption, telegram ignores it on the rest
    items = []
    for i, item in enumerate(media_list):
        caption = item.get("caption") if i == 0 else None
        entities = item.get("caption_entities") if i == 0 else None
        if item["type"] == "photo":
            items.append(InputMediaPhoto(media=item["file_id"], caption=caption, caption_entities=entities))
        elif item["type"] == "video":
            items.append(InputMediaVideo(media=item["file_id"], caption=caption, caption_entities=entities))
        elif item["type"] == "document":
            items.append(InputMediaDocument(media=item["file_id"], caption=caption, caption_entities=entities))
        elif item["type"] == "audio":
            items.append(InputMediaAudio(media=item["file_id"], caption=caption, caption_entities=entities))
    return items


async def safe_api_call(request, retries: int = MAX_RETRIES):
    for attempt in range(retries):
        try:
            return await request
        except TelegramRetryAfter as e:
            wait_time = e.retry_after + uniform(0.5, 2.0)
            logger.warning(f"flood control, waiting {wait_time:.1f}s")
            await asyncio.sleep(wait_time)
        except (TelegramForbiddenError, TelegramBadRequest):
            raise
        except Exception:
            if attempt < retries - 1:
                await asyncio.sleep(1)
            else:
                raise
    return None


async def send_one(bot, chat_id: int, media_list: List[Dict], text: Optional[str], text_entities, is_media_group: bool):
    if is_media_group and media_list:
        input_media = build_input_media(media_list)
        if not input_media:
            return None
        result = await safe_api_call(bot.send_media_group(chat_id, input_media))
        return result[0] if result else None

    if media_list and len(media_list) == 1:
        item = media_list[0]
        kind, file_id = item["type"], item["file_id"]
        opts = {"caption": text, "caption_entities": item.get("caption_entities") or text_entities}

        if kind == "photo":
            return await safe_api_call(bot.send_photo(chat_id, file_id, **opts))
        if kind == "video":
            return await safe_api_call(bot.send_video(chat_id, file_id, **opts))
        if kind == "document":
            return await safe_api_call(bot.send_document(chat_id, file_id, **opts))
        if kind == "audio":
            return await safe_api_call(bot.send_audio(chat_id, file_id, **opts))
        if kind == "voice":
            return await safe_api_call(bot.send_voice(chat_id, file_id, **opts))
        if kind == "video_note":
            return await safe_api_call(bot.send_video_note(chat_id, file_id))
        if kind == "sticker":
            return await safe_api_call(bot.send_sticker(chat_id, file_id))
        return None

    if text:
        return await safe_api_call(bot.send_message(chat_id, text, entities=text_entities))

    return None


async def multipost(
    bot,
    groups: List[Dict],
    media_list: Optional[List[Dict]] = None,
    text: Optional[str] = None,
    text_entities=None,
    is_media_group: bool = False,
    pin: bool = False,
    on_progress: Optional[Callable[[int, int], Awaitable[None]]] = None,
) -> Dict:
    media_list = media_list or []
    total = len(groups)
    success = 0
    errors = 0
    pin_errors = 0
    removed_ids = []

    for idx, group in enumerate(groups):
        try:
            sent = await send_one(bot, group["id"], media_list, text, text_entities, is_media_group)
            if sent:
                success += 1

            if pin and sent:
                try:
                    await safe_api_call(bot.pin_chat_message(
                        chat_id=group["id"], message_id=sent.message_id, disable_notification=True
                    ))
                except Exception as e:
                    logger.warning(f"could not pin in {group['id']}: {e}")
                    pin_errors += 1

            await asyncio.sleep(BASE_DELAY + uniform(0.02, 0.08))

            if on_progress and (idx + 1) % 5 == 0:
                await on_progress(idx + 1, total)

        except TelegramForbiddenError:
            logger.error(f"bot was removed from {group['id']}")
            errors += 1
            removed_ids.append(group["id"])
        except TelegramBadRequest as e:
            if "chat not found" in str(e).lower():
                removed_ids.append(group["id"])
            logger.error(f"send failed for {group['id']}: {e}")
            errors += 1
        except Exception as e:
            logger.error(f"send failed for {group['id']}: {e}")
            errors += 1

    return {
        "total": total,
        "success": success,
        "errors": errors,
        "pin_errors": pin_errors,
        "removed_ids": removed_ids,
    }
