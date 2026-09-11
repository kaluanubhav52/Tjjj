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
            "third_time_verified": default_date
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

    # ---------------- VERIFICATION TIME UPDATER (FIXED) ---------------- #

    async def update_verify_status(self, user_id: int, verify_level: int = 1):
        """
        User ki verification date update karta hai IST timezone ke hisab se.
        level 1 = last_verified
        level 2 = second_time_verified
        level 3 = third_time_verified
        """
        ist_tz = pytz.timezone('Asia/Kolkata')
        now_date = datetime.datetime.now(tz=ist_tz)
        
        field_map = {
            1: "last_verified",
            2: "second_time_verified",
            3: "third_time_verified"
        }
        
        field_name = field_map.get(verify_level, "last_verified")
        await self.update_notcopy_user(user_id, {field_name: now_date})

    # ---------------- 3-LEVEL VERIFICATION CHECK ---------------- #

    async def is_user_verified(self, user_id):
        """1st Verification Status"""
        user = await self.get_notcopy_user(user_id)
        past_date = user.get("last_verified")
        
        ist_tz = pytz.timezone('Asia/Kolkata')
        if not past_date or past_date.tzinfo is None:
            past_date = ist_tz.localize(past_date) if past_date else datetime.datetime(2019, 5, 17, 0, 0, 0, tzinfo=ist_tz)
        else:
            past_date = past_date.astimezone(ist_tz)
            
        current_time = datetime.datetime.now(tz=ist_tz)
        today_midnight = current_time.replace(hour=0, minute=0, second=0, microsecond=0)

        return past_date >= today_midnight

    async def user_verified(self, user_id):
        """2nd Verification Status"""
        user = await self.get_notcopy_user(user_id)
        past_date = user.get("second_time_verified")

        ist_tz = pytz.timezone('Asia/Kolkata')
        if not past_date or past_date.tzinfo is None:
            past_date = ist_tz.localize(past_date) if past_date else datetime.datetime(2019, 5, 17, 0, 0, 0, tzinfo=ist_tz)
        else:
            past_date = past_date.astimezone(ist_tz)
            
        current_time = datetime.datetime.now(tz=ist_tz)
        today_midnight = current_time.replace(hour=0, minute=0, second=0, microsecond=0)

        return past_date >= today_midnight

    async def use_second_shortener(self, user_id, time_gap):
        user = await self.get_notcopy_user(user_id)
        ist_tz = pytz.timezone('Asia/Kolkata')

        if not user.get("second_time_verified"):
            default_date = datetime.datetime(2019, 5, 17, 0, 0, 0, tzinfo=ist_tz)
            await self.update_notcopy_user(user_id, {"second_time_verified": default_date})
            user = await self.get_notcopy_user(user_id)

        if await self.is_user_verified(user_id):
            past_date = user.get("last_verified")
            if past_date.tzinfo is None:
                past_date = ist_tz.localize(past_date)
            else:
                past_date = past_date.astimezone(ist_tz)

            current_time = datetime.datetime.now(tz=ist_tz)
            time_difference = current_time - past_date

            if time_difference > datetime.timedelta(seconds=time_gap):
                second_time = user.get("second_time_verified")
                if second_time.tzinfo is None:
                    second_time = ist_tz.localize(second_time)
                else:
                    second_time = second_time.astimezone(ist_tz)

                return second_time < past_date
        return False

    async def use_third_shortener(self, user_id, time_gap):
        user = await self.get_notcopy_user(user_id)
        ist_tz = pytz.timezone('Asia/Kolkata')

        if not user.get("third_time_verified"):
            default_date = datetime.datetime(2018, 5, 17, 0, 0, 0, tzinfo=ist_tz)
            await self.update_notcopy_user(user_id, {"third_time_verified": default_date})
            user = await self.get_notcopy_user(user_id)

        if await self.user_verified(user_id):
            past_date = user.get("second_time_verified")
            if past_date.tzinfo is None:
                past_date = ist_tz.localize(past_date)
            else:
                past_date = past_date.astimezone(ist_tz)

            current_time = datetime.datetime.now(tz=ist_tz)
            time_difference = current_time - past_date

            if time_difference > datetime.timedelta(seconds=time_gap):
                third_time = user.get("third_time_verified")
                if third_time.tzinfo is None:
                    third_time = ist_tz.localize(third_time)
                else:
                    third_time = third_time.astimezone(ist_tz)

                return third_time < past_date
        return False

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

    # ---------------- OTHER DATABASE METHODS ---------------- #

    async def add_group(self, chat_id, title):
        if self.groups is None: return False
        group = await self.groups.find_one({'_id': chat_id})
        if not group:
            await self.groups.insert_one({'_id': chat_id, 'title': title})
            return True
        return False

    async def get_all_groups(self):
        return self.groups.find({})

    async def save_file(self, file_data):
        if self.files is None: return "error"
        exist = await self.files.find_one({'file_unique_id': file_data['file_unique_id']})
        if exist: return "duplicate"
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
            return []

db = Database()

# Shortlink API Generator
async def get_shortlink(url, grp_id=None, is_second_shortener=False, is_third_shortener=False):
    if is_third_shortener:
        api = config.SHORTENER_API3
        site = config.SHORTENER_WEBSITE3
    elif is_second_shortener:
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
        print(f"Shortener Error: {e}")
        return url
