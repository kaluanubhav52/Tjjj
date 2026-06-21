from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from database import db
from config import UPDATE_CHANNEL
from .utils import get_readable_size, clean_filename
import asyncio
# Fuzzywuzzy / Thefuzz import karein
from thefuzz import process

@Client.on_message(filters.text & ~filters.command(["start", "index", "newindex", "settings", "broadcast", "broadcast_groups", "stats", "restart", "clean", "channels", "watch", "font", "share", "tts", "paste"]))
async def search_handler(client, message):
    query = message.text
    if query.startswith("/"): return
    chat_id = message.chat.id
    
    if message.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        await db.add_group(chat_id, message.chat.title)
        settings = await db.get_settings(chat_id)
        if settings.get('search_trigger') == 'bang' and not query.startswith('!'): return
        if query.startswith('!'): query = query[1:].strip()
    else:
        settings = await db.get_settings(chat_id)

    if len(query) < 2: return

    # 1. Pehle exact matching files search karein
    results = await db.search_files(query)
    
    # 2. Agar koi result NAHI mila, toh hum SUGGESTIONS dikhayenge
    if not results:
        try:
            # Apne database se saari files ke titles fetch karein fuzzy matching ke liye
            # Note: Agar aapka database bohot bada hai, toh sirf top 500-1000 latest titles fetch karna behtar hoga performance ke liye.
            all_files = await db.get_all_file_names() # Make sure aapke database module mein yeh function ho ya jo saare names nikal sake
            
            # Agar titles list mil gayi, toh match nikalenge
            if all_files:
                # Top 4 matches nikalein jinka score 45% se upar ho
                matches = process.extract(query, all_files, limit=4)
                suggestions = [text for text, score in matches if score >= 45]
                
                if suggestions:
                    suggest_keyboard = []
                    for item in suggestions:
                        # Callback_data limit 64 bytes hoti hai, isliye string safe (max 40 chars) bhej rahe hain
                        suggest_keyboard.append([InlineKeyboardButton(f"🎬 {item[:45]}", callback_data=f"fuzz_{item[:40]}")])
                    
                    await message.reply_text(
                        f"**No results found for: `{query}`** <tg-emoji emoji-id='5924497670721769339'>🙅‍♂️</tg-emoji>\n\n"
                        f"🤔 **Did you mean one of these?**\n"
                        f"👇 Click on any button below to search directly:",
                        reply_markup=InlineKeyboardMarkup(suggest_keyboard),
                        quote=True
                    )
                    return

            # Agar koi close match bhi nahi mila, toh normal error msg
            msg = await message.reply(f"**No results found for: `{query}`** <tg-emoji emoji-id='5924497670721769339'>🙅‍♂️</tg-emoji>", quote=True)
            await asyncio.sleep(3)
            await msg.delete()
        except Exception as e:
            print(f"Error in suggestions: {e}")
        return

    try:
        await send_results_page(client, message, results, 1, query, settings)
    except Exception as e:
        print(f"Error sending results: {e}")

# 3. New Callback Handler for Suggestion Buttons Click
@Client.on_callback_query(filters.regex(r"^fuzz_"))
async def handle_suggestion_click(client, query: CallbackQuery):
    # Prefix hata kar clicked text nikalen
    suggested_query = query.data.replace("fuzz_", "")
    await query.answer(f"Searching for: {suggested_query}")
    
    # User ke click karne par fir se unhi results ko display kar denge jo exact match honge
    settings = await db.get_settings(query.message.chat.id)
    results = await db.search_files(suggested_query)
    
    if results:
        # Purane 'Did you mean' wale message ko direct results list se edit kar denge
        await send_results_page(client, query.message, results, 1, suggested_query, settings, is_edit=True)
    else:
        await query.answer("Could not find files for this suggestion.", show_alert=True)

@Client.on_callback_query(filters.regex(r"^dl_"))
async def handle_search_click(client, query: CallbackQuery):
    file_id = query.data.split("_")[1]
    bot_username = client.me.username
    await query.answer(url=f"https://t.me/{bot_username}?start={file_id}")

@Client.on_callback_query(filters.regex(r"^search#"))
async def search_pagination(client, query):
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
            prefix = chars[i] if i < len(chars) else str(i+1)
            clean = clean_filename(res['file_name'])
            file_id = str(res['_id'])
            link = f"https://t.me/{bot_username}?start={file_id}"
            text += f"🎬 **{prefix}. [{clean}]({link})**\n\n"

    nav = []
    if page > 1: nav.append(InlineKeyboardButton('⬅️', callback_data=f"search#{query}#{page-1}"))
    if page < total_pages: nav.append(InlineKeyboardButton('➡️', callback_data=f"search#{query}#{page+1}"))
    if nav: keyboard.append(nav)
    
    keyboard.append([InlineKeyboardButton(f"‏ ￶‏ ￶📃 Page {page}/{total_pages}", callback_data="noop")])

    markup = InlineKeyboardMarkup(keyboard)
    
    if is_edit:
        await message.edit_text(text, reply_markup=markup, disable_web_page_preview=True)
    else:
        await message.reply_text(text, reply_markup=markup, disable_web_page_preview=True, quote=True)
