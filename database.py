import motor.motor_asyncio
import re
import pytz
import datetime
import aiohttp
from bson.objectid import ObjectId
from config import MONGO_URI, DB_NAME
import config

class Database:
    def __init__(self):
        self._client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
        self.db = self._client[DB_NAME]
        self.files = None
        self.users = None
        self.groups = None
        self.settings = None
        self.watched = None
        self.banned = None
        self.banned_chats = None
        self.verify_id = None

    async def init_database(self, bot):
        me = await bot.get_me()
        prefix = me.username
        self.files = self.db[f"{prefix}_files"]
        self.users = self.db[f"{prefix}_users"]
        self.groups = self.db[f"{prefix}_groups"]
        self.settings = self.db[f"{prefix}_settings"]
        self.watched = self.db[f"{prefix}_watched"]
        self.banned = self.db[f"{prefix}_banned"]
        self.banned_chats = self.db[f"{prefix}_banned_chats"]
        self.verify_id = self.db[f"{prefix}_verify_id"]

    # ---------------- USER MANAGEMENT ---------------- #

    def new_user_verify_data(self, user_id):
        ist_timezone = pytz.timezone('Asia/Kolkata')
        default_date = datetime.datetime(2019, 5, 17, 0, 0, 0, tzinfo=ist_timezone)
        return {
            "user_id": user_id,
            "_id": user_id,
            "last_verified": default_date,
            "second_time_verified": default_date,
            "third_time_verified": default_date,
            "verify_level": 0,
            "is_premium": False
        }

    async def add_user(self, user_id, first_name):
        if self.users is None: return False
        user = await self.users.find_one({'_id': user_id})
        if not user:
            user_data = self.new_user_verify_data(user_id)
            user_data['first_name'] = first_name
            await self.users.insert_one(user_data)
            return True
        return False

    async def get_notcopy_user(self, user_id):
        if self.users is None: return None
        user = await self.users.find_one({'_id': user_id})
        if not user:
            user_data = self.new_user_verify_data(user_id)
            await self.users.insert_one(user_data)
            return user_data
        return user

    async def update_notcopy_user(self, user_id, value: dict):
        if self.users is None: return False
        return await self.users.update_one({'_id': user_id}, {'$set': value})

    async def get_all_users(self):
        return self.users.find({})

    async def has_premium_access(self, user_id: int):
        user = await self.get_notcopy_user(user_id)
        if not user: return False
        return user.get("is_premium", False)

    # ---------------- ADVANCE 3-LEVEL VERIFICATION SYSTEM ---------------- #

    def _parse_ist_datetime(self, date_val):
        """Converts naive or aware UTC/MongoDB timestamps to timezone-aware IST datetime"""
        ist_tz = pytz.timezone('Asia/Kolkata')
        default_date = datetime.datetime(2019, 5, 17, 0, 0, 0, tzinfo=ist_tz)
        
        if not date_val:
            return default_date
            
        if date_val.tzinfo is None:
            return ist_tz.localize(date_val)
        return date_val.astimezone(ist_tz)

    async def update_verify_status(self, user_id: int, verify_level: int):
        """Updates timestamp and exact level achieved by user"""
        ist_tz = pytz.timezone('Asia/Kolkata')
        now_date = datetime.datetime.now(tz=ist_tz)

        update_payload = {"verify_level": verify_level}

        if verify_level == 1:
            update_payload["last_verified"] = now_date
        elif verify_level == 2:
            update_payload["second_time_verified"] = now_date
        elif verify_level == 3:
            update_payload["third_time_verified"] = now_date

        await self.update_notcopy_user(user_id, update_payload)

    async def check_user_verification_needed(self, user_id: int):
        """
        Determines verification status and required level accurately.
        Returns: (needs_verification: bool, required_level: int)
        """
        user = await self.get_notcopy_user(user_id)
        if not user:
            return True, 1

        ist_tz = pytz.timezone('Asia/Kolkata')
        now_time = datetime.datetime.now(tz=ist_tz)

        v_level = user.get("verify_level", 0)

        last_v = self._parse_ist_datetime(user.get("last_verified"))
        second_v = self._parse_ist_datetime(user.get("second_time_verified"))
        third_v = self._parse_ist_datetime(user.get("third_time_verified"))

        # 1st Level: New user or never verified
        if v_level == 0 or (now_time - last_v).total_seconds() > (86400 * 365):
            return True, 1

        # 2nd Level: Level 1 clear ho chuka hai, check TWO_VERIFY_GAP
        if v_level == 1:
            time_diff = (now_time - last_v).total_seconds()
            if time_diff >= config.TWO_VERIFY_GAP:
                return True, 2
            return False, 0

        # 3rd Level: Level 2 clear ho chuka hai, check THREE_VERIFY_GAP
        if v_level == 2:
            time_diff = (now_time - second_v).total_seconds()
            if time_diff >= config.THREE_VERIFY_GAP:
                return True, 3
            return False, 0

        # Level 3 Complete: THREE_VERIFY_GAP ke baad restart from Level 2
        if v_level == 3:
            time_diff = (now_time - third_v).total_seconds()
            if time_diff >= config.THREE_VERIFY_GAP:
                return True, 2
            return False, 0

        return False, 0

    # ---------------- VERIFICATION TOKEN HANDLERS ---------------- #

    async def create_verify_id(self, user_id: int, hash: str):
        if self.verify_id is None: return None
        res = {"user_id": user_id, "hash": hash, "verified": False}
        return await self.verify_id.insert_one(res)

    async def get_verify_id_info(self, user_id: int, hash: str):
        if self.verify_id is None: return None
        return await self.verify_id.find_one({"user_id": user_id, "hash": hash})

    async def update_verify_id_info(self, user_id: int, hash: str, value: dict):
        if self.verify_id is None: return None
        return await self.verify_id.update_one({"user_id": user_id, "hash": hash}, {"$set": value})

    # ---------------- FILE MANAGEMENT ---------------- #

    async def save_file(self, file_data):
        if self.files is None: return "error"
        exist = await self.files.find_one({'file_unique_id': file_data['file_unique_id']})
        if exist:
            return "duplicate"
        await self.files.insert_one(file_data)
        return "saved"

    async def get_file(self, _id):
        if self.files is None: return None
        try:
            return await self.files.find_one({'_id': ObjectId(_id)})
        except Exception:
            try:
                return await self.files.find_one({'_id': str(_id)})
            except Exception:
                return None

    async def search_files(self, query):
        if self.files is None: return []
        clean_query = re.sub(r'[._\-]', ' ', query)
        words = clean_query.split()
        
        regex_list = [re.compile(re.escape(w), re.IGNORECASE) for w in words]
        cursor = self.files.find({"file_name": {"$all": regex_list}}).sort("_id", -1)
        return await cursor.to_list(length=1000)

    async def get_all_file_names(self):
        if self.files is None: return []
        try:
            cursor = self.files.find({}, {"file_name": 1, "_id": 0}).sort("_id", -1).limit(1500)
            results = await cursor.to_list(length=1500)
            return [doc["file_name"] for doc in results if "file_name" in doc]
        except Exception as e:
            print(f"Error fetching file names: {e}")
            return []

    # ---------------- GROUP & SETTINGS MANAGEMENT ---------------- #

    async def add_group(self, chat_id, title):
        if self.groups is None: return False
        group = await self.groups.find_one({'_id': chat_id})
        if not group:
            await self.groups.insert_one({'_id': chat_id, 'title': title})
            return True
        return False

    async def get_all_groups(self):
        return self.groups.find({})

    async def get_settings(self, chat_id):
        if self.settings is None:
            return {'results_per_page': 10, 'display_mode': 'inline', 'search_trigger': 'all', 'show_image': True}
        settings = await self.settings.find_one({'_id': chat_id})
        if not settings:
            return {'results_per_page': 10, 'display_mode': 'inline', 'search_trigger': 'all', 'show_image': True}
        return settings

    async def update_settings(self, chat_id, key, value):
        if self.settings is None: return
        await self.settings.update_one({'_id': chat_id}, {'$set': {key: value}}, upsert=True)

    async def add_watched_channel(self, chat_id):
        if self.watched is None: return
        await self.watched.update_one({'_id': chat_id}, {'$set': {'_id': chat_id}}, upsert=True)

    async def remove_watched_channel(self, chat_id):
        if self.watched is None: return
        await self.watched.delete_one({'_id': chat_id})

    async def get_watched_channels(self):
        if self.watched is None: return []
        channels = await self.watched.find({}).to_list(length=1000)
        return [c['_id'] for c in channels]

    # ---------------- BAN & MAINTENANCE SYSTEM ---------------- #

    async def delete_all_files(self):
        if self.files is None: return 0
        result = await self.files.delete_many({})
        return result.deleted_count

    async def delete_all_users(self):
        if self.users is None: return 0
        result = await self.users.delete_many({})
        return result.deleted_count

    async def delete_all_groups(self):
        if self.groups is None: return 0
        result = await self.groups.delete_many({})
        return result.deleted_count

    async def delete_file_by_unique_id(self, unique_id):
        if self.files is None: return
        await self.files.delete_one({'file_unique_id': unique_id})

    async def delete_files_by_chat_id(self, chat_id):
        if self.files is None: return 0
        result = await self.files.delete_many({'chat_id': chat_id})
        return result.deleted_count

    async def ban_user(self, user_id, reason="No reason specified"):
        if self.banned is None: return
        await self.banned.update_one(
            {'_id': user_id}, 
            {'$set': {'_id': user_id, 'reason': reason}}, 
            upsert=True
        )

    async def unban_user(self, user_id):
        if self.banned is None: return
        await self.banned.delete_one({'_id': user_id})

    async def get_ban_status(self, user_id):
        if self.banned is None: return None
        return await self.banned.find_one({'_id': user_id})

    async def ban_chat(self, chat_id, reason="No reason specified"):
        if self.banned_chats is None: return
        await self.banned_chats.update_one(
            {'_id': chat_id}, 
            {'$set': {'_id': chat_id, 'reason': reason}}, 
            upsert=True
        )

    async def unban_chat(self, chat_id):
        if self.banned_chats is None: return
        await self.banned_chats.delete_one({'_id': chat_id})

    async def get_chat_ban_status(self, chat_id):
        if self.banned_chats is None: return None
        return await self.banned_chats.find_one({'_id': chat_id})


# Dynamic Shortlink Resolver
async def get_shortlink(url, level=1):
    if level == 3:
        api = config.SHORTENER_API3
        site = config.SHORTENER_WEBSITE3
    elif level == 2:
        api = config.SHORTENER_API2
        site = config.SHORTENER_WEBSITE2
    else:
        api = config.SHORTENER_API
        site = config.SHORTENER_WEBSITE

    if not api or not site:
        return url

    site = site.replace("https://", "").replace("http://", "").strip("/")
    api_url = f"https://{site}/api?api={api}&url={url}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, timeout=10) as response:
                data = await response.json()
                if "shorturl" in data: return data["shorturl"]
                elif "url" in data: return data["url"]
                elif "link" in data: return data["link"]
                elif "shortenedUrl" in data: return data["shortenedUrl"]
                return url
    except Exception as e:
        print(f"Shortener Error ({site}): {e}")
        return url

db = Database()
