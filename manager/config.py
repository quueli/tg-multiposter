import os

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

BOT_TOKEN = os.getenv("MANAGER_BOT_TOKEN")

ADMINS = [int(x) for x in os.getenv("ADMIN_IDS", "123456789").split(",") if x.strip()]

# where users are told to go for a subscription
SUPPORT_CONTACT = os.getenv("SUPPORT_CONTACT", "@your_support")
MANAGER_BOT_USERNAME = os.getenv("MANAGER_BOT_USERNAME", "@your_manager_bot")

SUBSCRIPTION_PRICE = os.getenv("SUBSCRIPTION_PRICE", "10 credits")
SUBSCRIPTION_PERIOD = os.getenv("SUBSCRIPTION_PERIOD", "30 days")

DATA_FILE = os.path.join(BASE_DIR, "manager", "data.json")
INSTANCES_DIR = os.path.join(BASE_DIR, "instances")
TEMPLATE_DIR = os.path.join(BASE_DIR, "template")
