import os
from dotenv import load_dotenv

load_dotenv()

# Helper function for boolean conversion
def is_enabled(value, default=False):
    if isinstance(value, bool):
        return value
    return str(value).lower() in ["true", "1", "yes"]

# ============================
# Basic Bot Configuration
# ============================
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

MONGO_URI = os.environ.get("MONGO_URI", "")
DB_NAME = os.environ.get("DB_NAME", "TjBotDB")

ADMINS = [int(x) for x in os.environ.get("ADMINS", "").replace(",", " ").split() if x.strip().isdigit()]

LOG_CHANNEL = int(os.environ.get("LOG_CHANNEL", "0"))
LOG_VR_CHANNEL = int(os.environ.get("LOG_VR_CHANNEL", "0"))  # Verification Log Channel
UPDATE_CHANNEL = os.environ.get("UPDATE_CHANNEL", "freestoryhubMR")
REQUEST_GROUP = os.environ.get("REQUEST_GROUP", "https://t.me/pratilipifm0900")

PHOTO_URL = os.environ.get("PHOTO_URL", "https://i.ibb.co/v6b10BjN/03f383b6faeb.jpg")
VERIFY_IMG = os.environ.get("VERIFY_IMG", "https://telegra.ph/file/9ecc5d6e4df5b83424896.jpg")

AUTH_CHANNEL_FORCE = is_enabled(os.environ.get("AUTH_CHANNEL_FORCE", "true"), True)

# ============================
# Verification Settings
# ============================
IS_VERIFY = is_enabled(os.environ.get("IS_VERIFY", "True"), True)

# 12-to-12 Midnight Reset Mode (True = Daily 12:00 AM Reset)
MIDNIGHT_RESET = is_enabled(os.environ.get("MIDNIGHT_RESET", "True"), True)

# Tutorial Links
TUTORIAL = os.environ.get("TUTORIAL", "https://t.me/pratilipifm0900")
TUTORIAL_2 = os.environ.get("TUTORIAL_2", "https://t.me/pratilipifm0900")
TUTORIAL_3 = os.environ.get("TUTORIAL_3", "https://t.me/pratilipifm0900")

# Shortener 1 Details
SHORTENER_WEBSITE = os.environ.get("SHORTENER_WEBSITE", "")
SHORTENER_API = os.environ.get("SHORTENER_API", "")

# Shortener 2 Details
SHORTENER_WEBSITE2 = os.environ.get("SHORTENER_WEBSITE2", "")
SHORTENER_API2 = os.environ.get("SHORTENER_API2", "")
TWO_VERIFY_GAP = int(os.environ.get("TWO_VERIFY_GAP", "1200"))  # Default 20 Minutes (Gap between 1st and 2nd verification)

# Shortener 3 Details
SHORTENER_WEBSITE3 = os.environ.get("SHORTENER_WEBSITE3", "")
SHORTENER_API3 = os.environ.get("SHORTENER_API3", "")
THREE_VERIFY_GAP = int(os.environ.get("THREE_VERIFY_GAP", "54000")) # Default 15 Hours (Gap between 2nd and 3rd verification)
