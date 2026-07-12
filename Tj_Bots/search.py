from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from database import db
from config import UPDATE_CHANNEL
from .utils import get_readable_size, clean_filename
import asyncio
from thefuzz import process

# ⏱️ बैकग्राउंड टास्क: सजेशन्स को 1 मिनट में डिलीट करने के लिए
async def auto_delete_message(message, delay):
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except Exception:
        pass

# ⏳ बैकग्राउंड टास्क: सर्च रिज़ल्ट को 5 मिनट में एक्सपायर करने के लिए
async def auto_expire_results(message, delay):
    await asyncio.sleep(delay)
    try:
        await message.edit_text(
            text="⏳ **Time Expired!**\n\nयह सर्च रिज़ल्ट 5 मिनट पुराने होने के कारण सुरक्षा के लिए एक्सपायर हो गया है। कृपया दोबारा नाम लिखकर सर्च करें।",
            reply_markup=None
        )
    except Exception:
        pass

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

    # 1. Exact Database Search
    results = await db.search_files(query)
    
    # 2. If NO Results Found
    if not results:
        try:
            all_files = await db.get_all_file_names()
            suggestions = []
            
            if all_files:
                # Top 4 suggestions nikalenge jinka match 45% se upar ho
                matches = process.extract(query, all_files, limit=4)
                suggestions = [text for text, score in matches if score >= 45]
                
            if suggestions:
                # OPTION A: Agar close typos hain, toh fuzzy suggestions buttons dikhao
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
                # ⏰ 1 मिनट बाद सुझाव वाले मेसेज को डिलीट करने का टाइमर
                asyncio.create_task(auto_delete_message(suggest_msg, 60))
                return
            else:
                # OPTION B: Agar totally different word hai (Fuzzy fail), toh GOOGLE BUTTON OPTION do
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
                    f"Mujhe database mein isse milta-julta kuch nahi mila. Aap niche diye gaye button ka use karke Google par search kar sakte hain:",
                    reply_markup=InlineKeyboardMarkup(fail_keyboard),
                    quote=True
                )
                # ⏰ 1 मिनट बाद फेल मेसेज को डिलीट करने का टाइमर
                asyncio.create_task(auto_delete_message(fail_msg, 60))
                return

        except Exception as e:
            print(f"Error in suggestions/google fallback: {e}")
            try:
                await message.reply(f"**No results found for: `{query}`**", quote=True)
            except:
                pass
        return

    try:
        await send_results_page(client, message, results, 1, query, settings)
    except Exception as e:
        print(f"Error sending results: {e}")

# Callback Handler for Suggestion Buttons Click
@Client.on_callback_query(filters.regex(r"^fuzz_"))
async def handle_suggestion_click(client, query: CallbackQuery):
    suggested_query = query.data.replace("fuzz_", "")
    await query.answer(f"Searching for: {suggested_query}")
    
    settings = await db.get_settings(query.message.chat.id)
    results = await db.search_files(suggested_query)
    
    if results:
        # नई सर्च शुरू करने से पहले पुराने सजेशन मेसेज को डिलीट कर देते हैं
        try:
            await query.message.delete()
        except:
            pass
        await send_results_page(client, query.message, results, 1, suggested_query, settings, is_edit=False)
    else:
        await query.answer("Could not find files for this suggestion.", show_alert=True)

@Client.on_callback_query(filters.regex(r"^dl_"))
async def handle_search_click(client, query: CallbackQuery):
    file_id = query.data.split("_")[1]
    bot_username = client.me.username
    # बटन क्लिक करने पर यूजर सीधा बोट के PM में डीप-लिंक के साथ रीडायरेक्ट हो जाएगा
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
        res_msg = await message.reply_text(text, reply_markup=markup, disable_web_page_preview=True, quote=True)
        # ⏳ 5 मिनट का एक्सपायरी टाइमर यहाँ एक्टिवेट होगा (सिर्फ फ्रेश मेसेज भेजने पर)
        asyncio.create_task(auto_expire_results(res_msg, 300))
