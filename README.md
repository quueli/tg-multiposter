# tg-multiposter

![ci](https://github.com/quueli/tg-multiposter/actions/workflows/ci.yml/badge.svg)

post one message to a whole network of telegram chats, now or on a schedule. sold as a subscription: one manager bot, and every customer gets their own posting bot spun up from a template into its own directory and process.

manager/ is the bot i run. /add <token> checks the token, copies template/ into instances/<user>/, writes the .env and starts it as a subprocess. subscriptions are days per bot, a background loop starts and stops instances as they run out.

template/ is what the customer gets. it collects a post (albums are gathered over a 1s window so a 5 photo album goes out as one media group), shows a preview, then fans it out to every registered group. flood control: RetryAfter is respected with a bit of jitter, a "chat not found" or a kick drops that group from the list for good.

tests use a fake bot with one chat that answers 429 once and one that kicked us out:

    pip install -r requirements-dev.txt
    pytest

Dockerfile + compose.yaml run the manager. prices and the support contact are placeholders in manager/config.py.
