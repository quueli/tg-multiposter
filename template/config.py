import os

from dotenv import load_dotenv

load_dotenv()

# written per instance by the manager
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

ADMINS = [int(x) for x in os.getenv("ADMIN_IDS", "123456789").split(",") if x.strip()]
MAIN_BOT = os.getenv("MANAGER_BOT_USERNAME", "@your_manager_bot")

DATA_FILE = "data.json"
