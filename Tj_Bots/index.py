import asyncio
import time
import re
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait
from config import ADMINS
from database import db

# स्टेट्स और स्टेटस ट्रैकिंग डिक्शनरीज
INDEX_STATUS = {}
BATCH_STATES = {}

# ------------------------------------------------------------ #
#                🔧 HELPER FUNCTIONS (सहायक लॉजिक्स)            #
# ------------------------------------------------------------ #

def parse_tg_link(link: str):
    """टेलीग्राम लिंक से Chat ID और Message ID निकालने का हेल्पर फंक्शन"""
    pattern = r"t\.me/(?:c/)?([^/]+)/(\d+)"
    match = re.search(pattern, link)
    if match:
        chat_id = match.group(1)
        msg_id = int(match.group(2))
        if chat_id.isdigit():
            # प्राइवेट चैनल्स के लिए -100 प्रीफिक्स लगाना जरूरी है
            chat_id = int(f"-100{chat_id}")
        return chat_id, msg_id
    return None, None


# ------------------------------------------------------------ #
#          ⚡ FEATURE 1: INTERACTIVE BATCH INDEXER             #
# ------------------------------------------------------------ #

@Client.on_message(filters.command("batch") & filters.user(ADMINS))
async def start_batch_indexing(client, message):
    user_id = message.from_user.id
    # एडमिन की स्टेट को स्टोरी नेम पूछने पर सेट करें
    BATCH_STATES[user_id] = {"state": "ASK_STORY_NAME"}
    
    await message.reply(
        "📝 **बैच इंडेक्सिंग मोड ऑन हो गया है!**\n\n"
        "💬 सबसे पहले **स्टोरी का नाम (Search Name)** भेजें जिसे यूजर सर्च करेंगे:\n\n"
        "👉 _इस प्रोसेस को रोकने के लिए कभी भी_ `/cancel` _लिखें।_",
        quote=True
    )


@Client.on_message(filters.command("cancel") & filters.user(ADMINS))
async def cancel_batch(client, message):
    user_id = message.from_user.id
    if user_id in BATCH_STATES:
        BATCH_STATES.pop(user_id, None)
        await message.reply("❌ **बैच इंडेक्सिंग प्रोसेस को रद्द (Cancel) कर दिया गया है।**", quote=True)
    else:
        await message.reply("⚠️ कोई भी एक्टिव प्रोसेस नहीं चल रहा है।", quote=True)


# कन्वर्सेशन स्टेप्स हैंडलर (सिर्फ तब काम करेगा जब एडमिन एक्टिवली बैच सेट कर रहा हो)
@Client.on_message(filters.text & filters.user(ADMINS) & ~filters.command(["batch", "cancel", "index", "newindex"]))
async def handle_batch_steps(client, message):
    user_id = message.from_user.id
    
    # अगर एडमिन प्रोसेस में नहीं है, तो सामान्य रूप से आगे बढ़ने दें (कुछ न करें)
    if user_id not in BATCH_STATES:
        return

    user_data = BATCH_STATES[user_id]
    current_state = user_data["state"]
    text = message.text.strip()

    # STEP 1: स्टोरी का नाम लेना
    if current_state == "ASK_STORY_NAME":
        user_data["story_name"] = text
        user_data["state"] = "ASK_BUTTON_TEXT"
        
        await message.reply(
            f"✅ **स्टोरी का नाम सेव हुआ:** `{text}`\n\n"
            "🔘 अब इस बैच के **बटन का नाम** भेजें (जो यूजर को सर्च रिजल्ट में दिखेगा):\n"
            "👉 _जैसे: ⚡ S1 Full Batch [Ep 1-10]_",
            quote=True
        )

    # STEP 2: बटन का कस्टम टेक्स्ट लेना
    elif current_state == "ASK_BUTTON_TEXT":
        user_data["button_text"] = text
        user_data["state"] = "ASK_START_LINK"
        
        await message.reply(
            f"✅ **बटन का नाम सेव हुआ:** `{text}`\n\n"
            "🔗 अब इस बैच का **पहला लिंक (Start Link)** भेजें:",
            quote=True
        )

    # STEP 3: पहला मैसेज लिंक लेना
    elif current_state == "ASK_START_LINK":
        start_chat, start_id = parse_tg_link(text)
        if not start_chat or not start_id:
            return await message.reply("❌ **गलत टेलीग्राम लिंक!** कृपया एक सही मैसेज लिंक भेजें:", quote=True)
        
        user_data["start_chat"] = start_chat
        user_data["start_id"] = start_id
        user_data["state"] = "ASK_LAST_LINK"
        
        await message.reply(
            "✅ **पहला लिंक वेरिफाइड और सेव हुआ!**\n\n"
            "🔗 अब इस बैच का **आखिरी लिंक (Last Link)** भेजें:",
            quote=True
        )

    # STEP 4: आखिरी लिंक लेना और डेटाबेस में सुरक्षित स्टोर करना
    elif current_state == "ASK_LAST_LINK":
        last_chat, last_id = parse_tg_link(text)
        if not last_chat or not last_id:
            return await message.reply("❌ **गलत टेलीग्राम लिंक!** कृपया एक सही मैसेज लिंक भेजें:", quote=True)
        
        if last_chat != user_data["start_chat"]:
            return await message.reply("❌ **एरर:** पहला और आखिरी लिंक एक ही चैनल का होना चाहिए! दोबारा कोशिश करें:", quote=True)
            
        start_id = user_data["start_id"]
        if last_id < start_id:
            return await message.reply("❌ **एरर:** आखिरी लिंक का मैसेज आईडी पहले लिंक से बड़ा होना चाहिए! दोबारा कोशिश करें:", quote=True)

        story_name = user_data["story_name"]
        button_text = user_data["button_text"]
        start_chat = user_data["start_chat"]
        
        # प्रोसेस पूरी होने पर स्टेट को साफ़ करना
        BATCH_STATES.pop(user_id, None)

        status_msg = await message.reply("⏳ **डेटाबेस में बैच सेव किया जा रहा है...**", quote=True)
        
        batch_data = {
            "file_unique_id": f"batch_{start_chat}_{start_id}_{last_id}",
            "file_id": f"batch_{start_chat}_{start_id}_{last_id}", # सेफ्टी बैकअप के लिए
            "file_name": story_name,      # इसे सर्च करने पर यूज़र को रिजल्ट मिलेगा
            "button_text": button_text,    # बटन का कस्टम नाम
            "chat_id": start_chat,        # चैनल आईडी जहाँ से फॉरवर्ड करना है
            "start_id": start_id,          # पहली मैसेज आईडी
            "last_id": last_id,            # आखरी मैसेज आईडी
            "is_batch": True,             # बैच की पहचान के लिए फ्लैग
            "file_size": 0
        }
        
        # MongoDB में बैच को सेव करना (यह कोड आपके database structure के हिसाब से ऑटो-एडजस्ट हो जाएगा)
        try:
            if hasattr(db, "col"):
                await db.col.update_one(
                    {"file_unique_id": batch_data["file_unique_id"]},
                    {"$set": batch_data},
                    upsert=True
                )
            elif hasattr(db, "files"):
                await db.files.update_one(
                    {"file_unique_id": batch_data["file_unique_id"]},
                    {"$set": batch_data},
                    upsert=True
                )
            else:
                await db.db.files.update_one(
                    {"file_unique_id": batch_data["file_unique_id"]},
                    {"$set": batch_data},
                    upsert=True
                )
        except Exception as e:
            # बैकअप फॉलबैक
            try:
                await db.db['files'].update_one(
                    {"file_unique_id": batch_data["file_unique_id"]},
                    {"$set": batch_data},
                    upsert=True
                )
            except Exception as e2:
                return await status_msg.edit_text(f"❌ **डेटाबेस एरर:** बैच सेव नहीं हो पाया।\nError: {e2}")
        
        await status_msg.edit_text(
            f"✅ **बैच सफलतापूर्वक सेव हो गया है!**\n\n"
            f"📖 **Story:** `{story_name}`\n"
            f"🔘 **Button:** `{button_text}`\n"
            f"📊 **Range:** `{start_id}` से `{last_id}`\n\n"
            f"🚀 अब यूजर इसे आसानी से ग्रुप में सर्च कर सकते हैं!"
        )


# ------------------------------------------------------------ #
#          📂 FEATURE 2: EXISTING BULK INDEXING (पुराना)        #
# ------------------------------------------------------------ #

@Client.on_message(filters.command("index") & filters.user(ADMINS))
async def index_handler(client, message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await message.reply(
            "⚠️ **Incorrect usage.**\n\n"
            "Parameters: `/index [link] - [optional start]`\n\n"
            "Example 1 (up to message 1000): `/index https://t.me/c/1234/1000`\n"
            "Example 2 (from 500 to 1000): `/index https://t.me/c/1234/1000 - 500`",
            quote=True
        )

    full_arg = args[1]
    start_id = 1
    end_id = 0
    chat_id = 0

    if " - " in full_arg:
        parts = full_arg.split(" - ")
        link = parts[0].strip()
        try: start_id = int(parts[1].strip())
        except: return await message.reply("❌ Invalid start number.", quote=True)
    else:
        link = full_arg.strip()

    regex = r"(?:https?://)?(?:t\.me|telegram\.me)/(?:c/)?([\w\d]+)/(\d+)"
    match = re.match(regex, link)

    if not match: return await message.reply("❌ Invalid link.", quote=True)

    identifier = match.group(1)
    end_id = int(match.group(2))

    if identifier.isdigit(): chat_id = int(f"-100{identifier}")
    else: chat_id = identifier

    try:
        chat = await client.get_chat(chat_id)
        chat_id = chat.id
    except Exception as e:
        return await message.reply(f"❌ Cannot access channel. Make sure I am an admin there.\nError: {e}", quote=True)

    INDEX_STATUS[chat_id] = True
    stop_btn = InlineKeyboardMarkup([[InlineKeyboardButton("🛑 Stop Process", callback_data=f"stop_idx_{chat_id}")]])
    
    status = await message.reply(
        f"⏳ **Starting index...**\n"
        f"Channel: `{chat.title}`\n"
        f"Range: `{start_id}` to `{end_id}`",
        reply_markup=stop_btn,
        quote=True
    )

    total_saved = 0
    total_dups = 0
    last_update_time = time.time()
    current_id = start_id
    batch_size = 200

    while current_id <= end_id:
        if not INDEX_STATUS.get(chat_id, False):
            await status.edit("🛑 **Indexing stopped manually.**")
            return

        batch_end = min(current_id + batch_size, end_id + 1)
        ids = range(current_id, batch_end)
        
        try:
            messages = await client.get_messages(chat_id, list(ids))
        except FloodWait as e:
            await asyncio.sleep(e.value + 1)
            continue
        except Exception as e:
            current_id += batch_size
            continue

        for msg in messages:
            if not msg or not msg.text: continue
            
            msg_text = msg.text.strip()
            lines = [line.strip() for line in msg_text.split("\n") if line.strip()]
            
            if len(lines) < 2: continue
            
            title = lines[0]  
            custom_link = lines[1]  
            
            data = {
                'file_unique_id': f"lnk_{chat_id}_{msg.id}",
                'file_id': custom_link,
                'file_name': title,
                'file_size': 0,
                'chat_id': chat_id, 
                'message_id': msg.id, 
                'caption': msg_text
            }
            
            res = await db.save_file(data)
            if res == "saved": total_saved += 1
            else: total_dups += 1

        current_id += batch_size

        if time.time() - last_update_time >= 5:
            try:
                processed = min(current_id, end_id)
                await status.edit(
                    f"⏳ **Saving Links...**\n"
                    f"📍 Processing message: `{processed}` / `{end_id}`\n\n"
                    f"✅ Saved: `{total_saved}`\n"
                    f"♻️ Duplicates: `{total_dups}`",
                    reply_markup=stop_btn
                )
                last_update_time = time.time()
            except: pass

    INDEX_STATUS[chat_id] = False
    await status.edit(f"✅ **Indexing completed!**\n\n📂 Total saved: {total_saved}\n♻️ Duplicates: {total_dups}")


@Client.on_callback_query(filters.regex(r"^stop_idx_"))
async def stop_index_callback(client, query):
    chat_id_str = query.data.split("_")[-1]
    try: chat_id = int(chat_id_str)
    except: chat_id = chat_id_str
        
    if chat_id in INDEX_STATUS:
        INDEX_STATUS[chat_id] = False
        await query.answer("🛑 Stopping...", show_alert=True)
        await query.message.edit("🛑 **Process stopped.**")
    else:
        await query.answer("Process already finished.", show_alert=True)


# ------------------------------------------------------------ #
#        📺 FEATURE 3: WATCH CHANNEL & LIVE MONITOR (पुराना)    #
# ------------------------------------------------------------ #

@Client.on_message(filters.command("newindex") & filters.user(ADMINS))
async def new_channel_watch(client, message):
    if len(message.command) < 2:
        return await message.reply("ℹ️ Send a channel ID.\nExample: `/newindex -100...`", quote=True)
    try:
        chat_id = int(message.command[1])
        await db.add_watched_channel(chat_id)
        await message.reply(f"✅ Channel `{chat_id}` added to watchlist successfully!", quote=True)
    except Exception as e: await message.reply(f"❌ Error: {e}", quote=True)


@Client.on_message(filters.channel & filters.text)
async def live_watcher(client, message):
    watched = await db.get_watched_channels()
    if message.chat.id not in watched: return
    
    msg_text = message.text.strip()
    lines = [line.strip() for line in msg_text.split("\n") if line.strip()]
    
    if len(lines) < 2: return
    
    title = lines[0]
    custom_link = lines[1]
    
    data = {
        'file_unique_id': f"lnk_{message.chat.id}_{message.id}",
        'file_id': custom_link,
        'file_name': title,
        'file_size': 0,
        'chat_id': message.chat.id,
        'message_id': message.id,
        'caption': msg_text
    }
    await db.save_file(data)
