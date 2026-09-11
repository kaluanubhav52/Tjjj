import os
from dotenv import load_dotenv

load_dotenv()

def is_enabled(value, default=False):
    if isinstance(value, bool):
        return value
    return str(value).lower() in ["true", "1", "yes"]

# Basic Bot Configs
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

MONGO_URI = os.environ.get("MONGO_URI", "")
DB_NAME = os.environ.get("DB_NAME", "TjBotDB")

ADMINS = [int(x) for x in os.environ.get("ADMINS", "").replace(",", " ").split() if x.strip().isdigit()]

LOG_CHANNEL = int(os.environ.get("LOG_CHANNEL", "0"))
LOG_VR_CHANNEL = int(os.environ.get("LOG_VR_CHANNEL", "0"))
UPDATE_CHANNEL = os.environ.get("UPDATE_CHANNEL", "freestoryhubMR")
REQUEST_GROUP = os.environ.get("REQUEST_GROUP", "https://t.me/pratilipifm0900")

PHOTO_URL = os.environ.get("PHOTO_URL", "https://i.ibb.co/v6b10BjN/03f383b6faeb.jpg")
VERIFY_IMG = os.environ.get("VERIFY_IMG", "https://telegra.ph/file/9ecc5d6e4df5b83424896.jpg")

AUTH_CHANNEL_FORCE = is_enabled(os.environ.get("AUTH_CHANNEL_FORCE", "true"), True)

# ============================
# Verification Settings
# ============================
IS_VERIFY = is_enabled(os.environ.get("IS_VERIFY", "True"), True)

# Tutorial Links
TUTORIAL = os.environ.get("TUTORIAL", "https://t.me/dreamxbotz")
TUTORIAL_2 = os.environ.get("TUTORIAL_2", "https://t.me/dreamxbotz")
TUTORIAL_3 = os.environ.get("TUTORIAL_3", "https://t.me/dreamxbotz")

# Shortener 1 Details
SHORTENER_WEBSITE = os.environ.get("SHORTENER_WEBSITE", "arolinks.com")
SHORTENER_API = os.environ.get("SHORTENER_API", "d9e2ed76f4f30e39ccefc3455e5a8811a33cbe2f")

# Shortener 2 Details
SHORTENER_WEBSITE2 = os.environ.get("SHORTENER_WEBSITE2", "arolinks.com")
SHORTENER_API2 = os.environ.get("SHORTENER_API2", "d9e2ed76f4f30e39ccefc3455e5a8811a33cbe2f")
TWO_VERIFY_GAP = int(os.environ.get("TWO_VERIFY_GAP", "1200"))  # Default: 20 mins gap

# Shortener 3 Details
SHORTENER_WEBSITE3 = os.environ.get("SHORTENER_WEBSITE3", "arolinks.com")
SHORTENER_API3 = os.environ.get("SHORTENER_API3", "d9e2ed76f4f30e39ccefc3455e5a8811a33cbe2f")
THREE_VERIFY_GAP = int(os.environ.get("THREE_VERIFY_GAP", "54000")) # Default: 15 hours gap

# Message Scripts
VERIFICATION_TEXT = "⚠️ <b><u>First Verification Required!</u></b>\n\nAccess file to finish <b>1st Verification</b>."
SECOND_VERIFICATION_TEXT = "⚠️ <b><u>Second Verification Required!</u></b>\n\nAccess file to finish <b>2nd Verification</b>."
THIRDT_VERIFICATION_TEXT = "⚠️ <b><u>Third Verification Required!</u></b>\n\nAccess file to finish <b>3rd Verification</b>."
