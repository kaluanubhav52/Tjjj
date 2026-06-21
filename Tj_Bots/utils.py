import re
import time
from config import ADMINS

def get_readable_size(size):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TB"

def clean_filename(name):
    name = re.sub(r'\b(.mkv|.mp4|.avi)\b', '', name, flags=re.IGNORECASE)
    return re.sub(r'\s+', ' ', name).strip()

async def is_admin(client, chat_id, user_id):
    if user_id in ADMINS: return True
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status.name in ["OWNER", "ADMINISTRATOR"]
    except:
        return False

def get_readable_time(seconds: int) -> str:
    """
    Seconds ko readable string format mein convert karta hai.
    Example: 86400 -> "24 Hours", 3600 -> "1 Hour", 90000 -> "1 Day 1 Hour"
    """
    if seconds <= 0:
        return "0 Seconds"

    times = []
    # Time periods in seconds
    periods = [
        ("Day", 86400),
        ("Hour", 3600),
        ("Minute", 60),
        ("Second", 1)
    ]

    for name, period_seq in periods:
        if seconds >= period_seq:
            value = seconds // period_seq
            seconds %= period_seq
            # Plural (s) add karne ke liye agar value 1 se badi ho
            times.append(f"{value} {name}{'s' if value > 1 else ''}")

    return " ".join(times)

