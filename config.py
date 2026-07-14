import os
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

MONGO_URI = os.environ.get("MONGO_URI", "")
DB_NAME = "TjBotDB"

# Admins: You can add multiple admins separated by spaces or commas
ADMINS = [int(x) for x in os.environ.get("ADMINS", "").replace(",", " ").split()]

LOG_CHANNEL = int(os.environ.get("LOG_CHANNEL", "0"))
UPDATE_CHANNEL = "freestoryhubMR"
REQUEST_GROUP = "https://t.me/pratilipifm0900"

PHOTO_URL = "https://i.ibb.co/v6b10BjN/03f383b6faeb.jpg"

AUTH_CHANNEL_FORCE = os.environ.get("AUTH_CHANNEL_FORCE", "true").lower() == "true"
