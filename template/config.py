import os

from dotenv import load_dotenv

load_dotenv()

# set per instance by the manager when it provisions this copy
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

# manager bot users are pointed to when they want their own instance
MAIN_BOT = os.getenv("MANAGER_BOT_USERNAME", "@your_manager_bot")

DATA_FILE = "data.json"
