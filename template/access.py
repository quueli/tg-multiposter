from config import ADMINS, MAIN_BOT, OWNER_ID


def is_owner(user_id) -> bool:
    return user_id == OWNER_ID or user_id in ADMINS


def denied():
    return (
        "<b>Access denied</b>\n\n"
        "This bot belongs to someone else.\n\n"
        f"To get your own multiposting bot, talk to {MAIN_BOT}"
    )
