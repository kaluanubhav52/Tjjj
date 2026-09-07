import asyncio
import re
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from database import db
from config import UPDATE_CHANNEL
from .utils import get_readable_size, clean_filename
from thefuzz import process


# ⏱️ Background Task: Delete suggestions after 1 minute
async def auto_delete_message(message, delay):
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except Exception:
        pass


# ⏳ Background Task: Expire search results after 5 minutes
async def auto_expire_results(message, delay):
    await asyncio.sleep(delay)
    try:
        await message.edit_text(
            text="⏳ **Time Expired!**\n\nThis search result has expired for safety reasons after 5 minutes. Please type the name again to search.",
            reply_markup=None
        )
    except Exception:
        pass


@Client.on_message(filters.text & ~filters.command([
    "start", "index", "newindex", "settings", "broadcast", "broadcast_groups", 
    "stats", "restart", "clean", "channels", "watch", "font", "share", "tts", "paste"
]))
async def search_handler(client, message):
    query = message.text.strip()
    if query.startswith("/"):
        return
    
    chat_id = message.chat.id
    
    if message.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        await db.add_group(chat_id, message.chat.title)
        settings = await db.get_settings(chat_id)
        if settings.get('search_trigger') == 'bang' and not query.startswith('!'):
            return
        if query.startswith('!'):
            query = query[1:].strip()
    else:
        settings = await db.get_settings(chat_id)

    if len(query) < 2:
        return

    # ---------------------------------------------------------
    # 🎧 EPISODIC RANGE EXTRACTION LOGIC
    # Detects patterns like: "My Possessive Ep 6", "My Possessive Episode 06", "My Possessive Ep.6"
    # ---------------------------------------------------------
    ep_pattern = re.search(r'^(.*?)\s*(?:ep|episode|e)\.?\s*(\d+)', query, re.IGNORECASE)
    extracted_series_name = None
    requested_ep_num = None

    if ep_pattern:
        extracted_series_name = ep_pattern.group(1).strip()
        requested_ep_num = int(ep_pattern.group(2))

    # 1. Exact Database Search
    results = await db.search_files(query)

    # 2. Episode Range Fallback Search (e.g., handles searching "Ep 6" inside "1 To 10" file)
    if not results and extracted_series_name:
        series_results = await db.search_files(extracted_series_name)
        matched_range_files = []

        for file_doc in series_results:
            file_name = file_doc.get("file_name", "")
            
            # Matches ranges like "1 To 10", "1-10", "Ep 01-10", "Episode 1 to 10"
            range_match = re.search(r'(?:ep|episode)?\s*(\d+)\s*(?:to|-)\s*(\d+)', file_name, re.IGNORECASE)
            
            if range_match:
                start_ep = int(range_match.group(1))
                end_ep = int(range_match.group(2))
                
                # Check if requested episode falls inside range
                if start_ep <= requested_ep_num <= end_ep:
                    matched_range_files.append(file_doc)

        if matched_range_files:
            results = matched_range_files

    # 3. If NO Results Found
    if not results:
        try:
            all_files = await db.get_all_file_names()
            suggestions = []
            
            if all_files:
                matches = process.extract(query, all_files, limit=4)
                suggestions = [text for text, score in matches if score >= 45]
                
            if suggestions:
                suggest_keyboard = []
                for item in suggestions:
                    suggest_keyboard.append([InlineKeyboardButton(f"🎬 {item[:45]}", callback_data=f"fuzz_{item[:40]}")])
                
                suggest_msg = await message.reply_text(
                    f"**No results found for: `{query}`** <tg-emoji emoji-id='5924497670721769339'>🙅‍♂️</tg-emoji>\n\n"
                    f"🤔 **Did you mean one of these?**\n"
                    f"👇 Click on any button below to search directly:",
                    reply_markup=InlineKeyboardMarkup(suggest_keyboard),
                    quote=True
                )
                asyncio.create_task(auto_delete_message(suggest_msg, 60))
                return
            else:
                google_encoded_query = query.replace(" ", "+")
                google_url = f"https://www.google.com/search?q={google_encoded_query}"
                
                fail_keyboard = [
                    [
                        InlineKeyboardButton("🌐 Search on Google", url=google_url)
                    ],
                    [
                        InlineKeyboardButton("📢 Request on Group", url="https://t.me/your_support_group") 
                    ]
                ]
                
                fail_msg = await message.reply_text(
                    f"**No results found for: `{query}`** <tg-emoji emoji-id='5924497670721769339'>🙅‍♂️</tg-emoji>\n\n"
                    f"I couldn't find anything similar in the database. You can search on Google using the button below:",
                    reply_markup=InlineKeyboardMarkup(fail_keyboard),
                    quote=True
                )
                asyncio.create_task(auto_delete_message(fail_msg, 60))
                return

        except Exception as e:
            print(f"Error in suggestions/google fallback: {e}")
            try:
                await message.reply(f"**No results found for: `{query}`**", quote=True)
            except Exception:
                pass
        return

    try:
        await send_results_page(client, message, results, 1, query, settings)
    except Exception as e:
        print(f"Error sending results: {e}")


# Callback Handler for Suggestion Buttons
@Client.on_callback_query(filters.regex(r"^fuzz_"))
async def handle_suggestion_click(client, query: CallbackQuery):
    suggested_query = query.data.replace("fuzz_", "")
    await query.answer(f"Searching for: {suggested_query}")
    
    settings = await db.get_settings(query.message.chat.id)
    results = await db.search_files(suggested_query)
    
    if results:
        try:
            await query.message.delete()
        except Exception:
            pass
        await send_results_page(client, query.message, results, 1, suggested_query, settings, is_edit=False)
    else:
        await query.answer("Could not find files for this suggestion.", show_alert=True)


# Callback Handler for File Link Click
@Client.on_callback_query(filters.regex(r"^dl_"))
async def handle_search_click(client, query: CallbackQuery):
    file_id = query.data.split("_")[1]
    bot_username = client.me.username
    await query.answer(url=f"https://t.me/{bot_username}?start={file_id}")


# Callback Handler for Pagination Buttons
@Client.on_callback_query(filters.regex(r"^search#"))
async def search_pagination(client, query: CallbackQuery):
    try:
        _, q_str, page_str = query.data.split("#")
        page = int(page_str)
        settings = await db.get_settings(query.message.chat.id)
        results = await db.search_files(q_str)
        
        if not results:
            return await query.answer("Search expired.", show_alert=True)
            
        await send_results_page(client, query.message, results, page, q_str, settings, is_edit=True)
    except Exception as e:
        print(f"Error in pagination: {e}")


async def send_results_page(client, message, results, page, query, settings, is_edit=False):
    per_page = settings.get('results_per_page', 10)
    total_results = len(results)
    total_pages = (total_results + per_page - 1) // per_page
    
    start_idx = (page - 1) * per_page
    current_batch = results[start_idx : start_idx + per_page]
    
    bot_username = client.me.username or "Bot"

    text = f"<b><tg-emoji emoji-id='5319230516929502602'>🔍</tg-emoji></b> <b><i><u>Search Results</u></i></b> <tg-emoji emoji-id='5452069934089641166'>❓</tg-emoji>\n\n"
    text += f"<blockquote><b><tg-emoji emoji-id='5397782960512444700'>📌</tg-emoji></b>   <b>Query:</b> <code>{query}</code></blockquote>\n"
    text += f"<blockquote><b><tg-emoji emoji-id='5282843764451195532'>🖥</tg-emoji></b>   <b>Results:</b> <code>{total_results}</code></blockquote>\n"
    text += "\n**<tg-emoji emoji-id='5406745015365943482'>⬇️</tg-emoji><tg-emoji emoji-id='5406745015365943482'>⬇️</tg-emoji><tg-emoji emoji-id='5406745015365943482'>⬇️</tg-emoji>**\n\n"
    text += "⏳ _This message will automatically expire in 5 minutes..._\n\n"
    
    keyboard = []
    display_mode = settings.get('display_mode', 'inline')

    if display_mode == 'inline':
        for res in current_batch:
            clean = clean_filename(res['file_name'])
            size = get_readable_size(res['file_size'])
            btn_text = f"[{size}] {clean}"
            file_id = str(res['_id'])
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"dl_{file_id}")])
            
    else:
        chars = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10']
        for i, res in enumerate(current_batch):
            prefix = chars[i] if i < len(chars) else str(i + 1)
            clean = clean_filename(res['file_name'])
            file_id = str(res['_id'])
            link = f"https://t.me/{bot_username}?start={file_id}"
            text += f"🎬 **{prefix}. [{clean}]({link})**\n\n"

    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton('⬅️', callback_data=f"search#{query}#{page-1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton('➡️', callback_data=f"search#{query}#{page+1}"))
    if nav:
        keyboard.append(nav)
    
    keyboard.append([InlineKeyboardButton(f"‏ ￶‏ ￶📃 Page {page}/{total_pages}", callback_data="noop")])

    markup = InlineKeyboardMarkup(keyboard)
    
    if is_edit:
        await message.edit_text(text, reply_markup=markup, disable_web_page_preview=True)
    else:
        res_msg = await message.reply_text(text, reply_markup=markup, disable_web_page_preview=True, quote=True)
        asyncio.create_task(auto_expire_results(res_msg, 300))
