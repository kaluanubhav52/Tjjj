import asyncio
import time
import re
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait
from config import ADMINS
from database import db

INDEX_STATUS = {}

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
            if not msg or not msg.media: continue
            if msg.media not in [enums.MessageMediaType.VIDEO, enums.MessageMediaType.DOCUMENT, enums.MessageMediaType.AUDIO]: continue
            
            media = getattr(msg, msg.media.value, None)
            if not media: continue
            
            file_name = getattr(media, 'file_name', None) or msg.caption or f"File {msg.id}"
            data = {
                'file_unique_id': media.file_unique_id, 'file_id': media.file_id,
                'file_name': file_name, 'file_size': media.file_size,
                'chat_id': chat_id, 'message_id': msg.id, 'caption': msg.caption or ""
            }
            res = await db.save_file(data)
            if res == "saved": total_saved += 1
            else: total_dups += 1

        current_id += batch_size

        if time.time() - last_update_time >= 5:
            try:
                processed = min(current_id, end_id)
                await status.edit(
                    f"⏳ **Saving files...**\n"
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

@Client.on_message(filters.command("newindex") & filters.user(ADMINS))
async def new_channel_watch(client, message):
    if len(message.command) < 2:
        return await message.reply("ℹ️ Send a channel ID.\nExample: `/newindex -100...`", quote=True)
    try:
        chat_id = int(message.command[1])
        await db.add_watched_channel(chat_id)
        await message.reply(f"✅ Channel `{chat_id}` added to watchlist successfully!", quote=True)
    except Exception as e: await message.reply(f"❌ Error: {e}", quote=True)

@Client.on_message(filters.channel)
async def live_watcher(client, message):
    watched = await db.get_watched_channels()
    if message.chat.id not in watched or not message.media: return
    
    if message.media not in [enums.MessageMediaType.VIDEO, enums.MessageMediaType.DOCUMENT, enums.MessageMediaType.AUDIO]: return

    media = getattr(message, message.media.value, None)
    if not media: return

    file_name = getattr(media, 'file_name', None) or message.caption or f"File {message.id}"
    data = {
        'file_unique_id': media.file_unique_id, 'file_id': media.file_id,
        'file_name': file_name, 'file_size': media.file_size,
        'chat_id': message.chat.id, 'message_id': message.id, 'caption': message.caption or ""
    }
    await db.save_file(data)
