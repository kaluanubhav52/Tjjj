import asyncio
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, InputMediaPhoto
from pyrogram.errors import FloodWait
from bson import ObjectId  # बैच आईडी फेच करने के लिए जरूरी है
from config import UPDATE_CHANNEL, REQUEST_GROUP, PHOTO_URL, ADMINS, LOG_CHANNEL, AUTH_CHANNEL_FORCE
from database import db

# ------------------------------------------------------------ #
#                        LINK SEND HELPER                       #
# ------------------------------------------------------------ #
async def send_link_message(client, chat_id, file_data, reply_to_id=None):
    """यूजर को स्टोरी का नाम और उसका कस्टम लिंक सेंड करने के लिए helper function"""
    title = file_data.get('file_name', 'Story')
    custom_link = file_data.get('file_id') # डेटाबेस में सुरक्षित लिंक
    
    if not custom_link:
        return False

    text = (
        f"<b><tg-emoji emoji-id='5397782960512444700'>📌</tg-emoji> यहाँ आपकी स्टोरी का लिंक है:</b>\n\n"
        f"🔹 <b>Name:</b> <code>{title}</code>\n\n"
        f"🔗 <b>Link:</b> {custom_link}\n\n"
        f"<i>🚀 लिंक पर क्लिक करके आप अपनी स्टोरी देख सकते हैं।</i>"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Open Link", url=custom_link)]
    ])

    try:
        await client.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=keyboard,
            reply_to_message_id=reply_to_id,
            disable_web_page_preview=True
        )
        return True
    except Exception as e:
        print(f"Error sending link message: {e}")
        return False

# ------------------------------------------------------------ #
#                       BATCH SEND HELPER                      #
# ------------------------------------------------------------ #
async def send_batch_messages(client, chat_id, batch_db_id, reply_to_id=None):
    """डेटाबेस से बैच डेटा उठाकर यूजर को सारे मैसेजेस एक-एक करके फॉरवर्ड करने वाला हेल्पर"""
    try:
        # सुरक्षित रूप से अलग-अलग कलेक्शन फॉर्मेट्स को हैंडल करना
        if hasattr(db, "col"):
            batch_data = await db.col.find_one({"_id": ObjectId(batch_db_id)})
        elif hasattr(db, "files"):
            batch_data = await db.files.find_one({"_id": ObjectId(batch_db_id)})
        else:
            batch_data = await db.db.files.find_one({"_id": ObjectId(batch_db_id)})
    except Exception as e:
        print(f"Database batch fetch error: {e}")
        batch_data = None
        
    if not batch_data:
        return False, "❌ यह बैच उपलब्ध नहीं है या डेटाबेस से डिलीट हो चुका है।"

    from_chat = batch_data.get("chat_id")
    start_id = batch_data.get("start_id")
    last_id = batch_data.get("last_id")
    story_name = batch_data.get("file_name")

    progress_msg = await client.send_message(
        chat_id=chat_id,
        text=f"⏳ **प्रक्रिया शुरू हो रही है...**\n`{story_name}` के सभी एपिसोड्स भेजे जा रहे हैं।",
        reply_to_message_id=reply_to_id
    )
    
    sent_count = 0
    for msg_id in range(start_id, last_id + 1):
        try:
            # copy_message बिना "Forwarded From" टैग के मैसेज सेंड करता है
            await client.copy_message(
                chat_id=chat_id,
                from_chat_id=from_chat,
                message_id=msg_id
            )
            sent_count += 1
            await asyncio.sleep(0.5)  # टेलीग्राम की लिमिट्स (Flood Limit) से सुरक्षा के लिए
        except FloodWait as e:
            await asyncio.sleep(e.value + 1)
            # री-ट्राई करना
            try:
                await client.copy_message(chat_id=chat_id, from_chat_id=from_chat, message_id=msg_id)
                sent_count += 1
            except:
                pass
        except Exception as e:
            print(f"Error copying msg {msg_id}: {e}")
            continue
    
    await progress_msg.edit_text(
        f"✅ **कार्य पूर्ण!**\n`{story_name}` के कुल `{sent_count}` मैसेजेस सफलतापूर्वक भेज दिए गए हैं।"
    )
    return True, None

# ------------------------------------------------------------ #
#                           START CMD                           #
# ------------------------------------------------------------ #
@Client.on_message(filters.command("start"))
async def start_command(client, message):
    if message.chat.type == enums.ChatType.PRIVATE:
        user_id = message.from_user.id

        # Handle direct link sharing via start parameter (Deep Linking)
        if len(message.command) > 1:
            file_db_id = message.command[1]

            # Channel subscription check
            should_check = AUTH_CHANNEL_FORCE
            is_subbed = True
            if should_check:
                try:
                    await client.get_chat_member(UPDATE_CHANNEL, user_id)
                except:
                    is_subbed = False

            if not is_subbed:
                btn = [
                    [InlineKeyboardButton('📣 Join Channel', url=f'https://t.me/{UPDATE_CHANNEL}')],
                    [InlineKeyboardButton('↻ Try Again', callback_data=f"checksub_{file_db_id}")]
                ]
                return await message.reply_text(
                    "**To use this bot you must subscribe to its update channel! 🫰**",
                    reply_markup=InlineKeyboardMarkup(btn),
                    quote=True
                )

            # 🚀 बैच या सिंगल फ़ाइल डिसीजन मेकर
            if file_db_id.startswith("batch_"):
                batch_id = file_db_id.replace("batch_", "")
                success, err = await send_batch_messages(client, message.chat.id, batch_id, message.id)
                if not success:
                    await message.reply(err or "❌ Error processing batch link.", quote=True)
            else:
                file_data = await db.get_file(file_db_id)
                if file_data:
                    success = await send_link_message(client, message.chat.id, file_data, message.id)
                    if not success:
                        await message.reply("❌ The link was deleted or inaccessible.", quote=True)
            return

        # Normal start animation and home message
        bot_name = client.me.first_name
        bot_username = client.me.username
        bot_mention = f"[{bot_name}](https://t.me/{bot_username})"

        anim_msg = await message.reply_text(
            f"<blockquote>**__Hey 👋__**\n**__Welcome to {bot_mention} 😎__**</blockquote>",
            quote=True
        )
        await asyncio.sleep(1.0)
        await anim_msg.edit_text("⚡️")
        await asyncio.sleep(0.8)
        await anim_msg.edit_text("**__Starting bot...__** 😈")
        await asyncio.sleep(0.7)

        await send_home_message(client, message)
        await anim_msg.delete()

    elif message.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        await message.reply("Hey! I'm ready to search for stories 📖", quote=True)

# ------------------------------------------------------------ #
#                      GROUP ADD HANDLER                        #
# ------------------------------------------------------------ #
@Client.on_message(filters.new_chat_members)
async def added_to_group(client, message):
    for member in message.new_chat_members:
        if member.id == client.me.id:
            await message.reply(
                "Thanks for adding me! 📖\n"
                "Send the name of the story you want to search for.",
                quote=True
            )

# ------------------------------------------------------------ #
#                         HOME MESSAGE                          #
# ------------------------------------------------------------ #
async def send_home_message(client, message, user=None, is_edit=False):
    if not user:
        user = message.from_user

    user_mention = user.mention
    bot_name = client.me.first_name
    bot_username = client.me.username
    bot_mention = f"[{bot_name}](https://t.me/{bot_username})"

    buttons = [
        [InlineKeyboardButton("🔍 Online Search 🔎", switch_inline_query_current_chat="", style=enums.ButtonStyle.PRIMARY)],
        [InlineKeyboardButton('✇ Group ✇', url=REQUEST_GROUP, style=enums.ButtonStyle.SUCCESS),
         InlineKeyboardButton('✇ Updates ✇', url=f'https://t.me/{UPDATE_CHANNEL}', style=enums.ButtonStyle.SUCCESS)],
        [InlineKeyboardButton('〄 Help 〄', callback_data='help', style=enums.ButtonStyle.PRIMARY),
         InlineKeyboardButton('⍟ About ⍟', callback_data='about', style=enums.ButtonStyle.PRIMARY)],
        [InlineKeyboardButton('⇋ Add to Group ⇋', url=f"http://t.me/{client.me.username}?startgroup&admin=delete_messages", style=enums.ButtonStyle.SUCCESS)]
    ]

    txt = (
        f"**Hey {user_mention} 👋**\n"
        f"**Welcome to {bot_mention}** 😎\n\n"
        "**I am an innovative story and custom link search engine,**\n"
        "<b>My job is to search for stories in groups,\n"
        "Add me to your group and I'll take it from here.</b> ☄️\n\n"
        "<blockquote>**👨🏼‍💻 Lead Developer: @TJ_Bots_Admin**</blockquote>"
    )

    if is_edit:
        await message.edit_media(InputMediaPhoto(PHOTO_URL, caption=txt), reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await message.reply_photo(PHOTO_URL, caption=txt, reply_markup=InlineKeyboardMarkup(buttons), quote=True)

# ------------------------------------------------------------ #
#                        CALLBACK HANDLER                       #
# ------------------------------------------------------------ #
@Client.on_callback_query()
async def callback_handler(client, query: CallbackQuery):
    data = query.data
    user_id = query.from_user.id

    # Handle subscription check for files/links
    if data.startswith("checksub_"):
        file_db_id = data.replace("checksub_", "") # स्प्लिट एरर बग यहाँ फिक्स कर दिया गया है
        should_check = AUTH_CHANNEL_FORCE
        is_subbed = True

        if should_check:
            try:
                await client.get_chat_member(UPDATE_CHANNEL, user_id)
            except:
                is_subbed = False

        if not is_subbed:
            return await query.answer("❌ You must join the update channel first!", show_alert=True)

        reply_to = query.message.reply_to_message.id if query.message.reply_to_message else None

        # 🚀 फ़ोर्स सब चेकिंग के बाद बैच या सिंगल का फैसला
        if file_db_id.startswith("batch_"):
            batch_id = file_db_id.replace("batch_", "")
            success, err = await send_batch_messages(client, query.message.chat.id, batch_id, reply_to)
            if success:
                await query.message.delete()
            else:
                await query.answer(err or "❌ Batch not found or inaccessible.", show_alert=True)
        else:
            file_data = await db.get_file(file_db_id)
            if file_data:
                success = await send_link_message(client, query.message.chat.id, file_data, reply_to)
                if success:
                    await query.message.delete()
                else:
                    await query.answer("❌ Link not found or inaccessible.", show_alert=True)
            else:
                await query.answer("❌ Link not found in database.", show_alert=True)
        return

    # Admin-only protection
    if data == "help_admin" and user_id not in ADMINS:
        return await query.answer("⛔ Admins only.", show_alert=True)

    # Clear media on non-critical callbacks
    if data not in ["closea", "noop", "help_stats"]:
        try:
            await query.message.edit_media(InputMediaPhoto(PHOTO_URL, caption=""), reply_markup=None)
            await asyncio.sleep(0.1)
        except:
            pass

    # -------------------- MENU NAVIGATION --------------------
    if data == "home":
        await send_home_message(client, query.message, user=query.from_user, is_edit=True)

    elif data == "help":
        user_mention = query.from_user.mention
        btns = [
            [InlineKeyboardButton('Group Settings', callback_data='help_settings', style=enums.ButtonStyle.SUCCESS),
             InlineKeyboardButton('© Copyright', callback_data='help_copyright', style=enums.ButtonStyle.SUCCESS)],
            [InlineKeyboardButton('Extra Tools', callback_data='help_extra', style=enums.ButtonStyle.SUCCESS),
             InlineKeyboardButton('User Guide', callback_data='help_guide', style=enums.ButtonStyle.SUCCESS)],
            [InlineKeyboardButton('TikTok Downloader', callback_data='help_d', style=enums.ButtonStyle.SUCCESS),
             InlineKeyboardButton('Stats', callback_data='help_stats', style=enums.ButtonStyle.SUCCESS)],
            [InlineKeyboardButton('🆕 Telegraph', callback_data='help_telegraph', style=enums.ButtonStyle.PRIMARY),
             InlineKeyboardButton('🆕 Video Tools', callback_data='help_exthumb', style=enums.ButtonStyle.PRIMARY)],
            [InlineKeyboardButton('🏠 Home 🏠', callback_data='home', style=enums.ButtonStyle.DANGER)],
        ]
        if user_id in ADMINS:
            btns.insert(0, [InlineKeyboardButton('👮‍♂️ Admin Commands 👮‍♂️', callback_data='help_admin', style=enums.ButtonStyle.DANGER)])

        await query.message.edit_media(
            InputMediaPhoto(PHOTO_URL, caption=f"<b>Hey {user_mention},\nHere you can get help for all my commands.</b>"),
            reply_markup=InlineKeyboardMarkup(btns)
        )

    # -------------------- EXTRA TOOLS --------------------
    elif data == "help_extra":
        txt = (
            "<b><u>Extra Tools:</u></b>\n\n"
            "<b>◉ Text Font:</b>\n"
            "<blockquote>• <code>/font</code> [text] - Converts English text to special fonts.</blockquote>\n\n"
            "<b>◉ Share Text:</b>\n"
            "<blockquote>• <code>/share</code> [text] - Creates a quick share link for the text you wrote.</blockquote>\n\n"
            "<b>◉ Text to Speech (TTS):</b>\n"
            "<blockquote>• <code>/tts</code> - Reply to a text message, and the bot will send it back as a voice message.</blockquote>\n\n"
            "<b>◉ Paste Text:</b>\n"
            "<blockquote>• <code>/paste</code> - Reply to text or a file to upload it to Pastebin and get a link.</blockquote>\n\n"
            "<b>◉ User Info:</b>\n"
            "<blockquote>• <code>/id</code> - User ID / Chat ID.</blockquote>\n"
            "<blockquote>• <code>/info</code> - Information about a user account, profile, name, username, etc...</blockquote>\n\n"
            "<b>◉ Sticker ID</b>\n"
            "<blockquote>• <code>/stickerid</code> - Gets the ID of the sticker you replied to.</blockquote>\n\n"
            "<b>◉ System Tools:</b>\n"
            "<blockquote>• <code>/json</code> - Get the technical (JSON) info of the message.</blockquote>\n"
            "<blockquote>• <code>/written</code> [file name] - Converts the text into a text file.</blockquote>"
        )
        back_btn = InlineKeyboardMarkup([[InlineKeyboardButton('← Back', callback_data='help', style=enums.ButtonStyle.PRIMARY)]])
        await query.message.edit_media(InputMediaPhoto(PHOTO_URL, caption=txt), reply_markup=back_btn)

    # -------------------- ADMIN COMMANDS --------------------
    elif data == "help_admin":
        txt = (
            "<b><u>Admin Control Panel:</u></b>\n\n"
            "<b>◉ Content Management:</b>\n"
            "<blockquote>• <code>/index</code> [link] - [start] - Add links from a channel text (by range).\n"
            "• <code>/batch</code> - Build customizable interactive episode batches (Interactive Setup).\n"
            "• <code>/newindex</code> [ID] - Track new text content in a channel.\n"
            "• <code>/channels</code> - Manage tracked channels.</blockquote>\n\n"
            "<b>◉ Users and Groups:</b>\n"
            "<blockquote>• <code>/ban</code> [ID] - Ban a user.\n"
            "• <code>/unban</code> [ID] - Unban a user.\n"
            "• <code>/ban_chat</code> [ID] - Ban a group.\n"
            "• <code>/unban_chat</code> [ID] - Unban a group.\n"
            "• <code>/leave</code> [ID] - Leave a group (without banning).</blockquote>\n\n"
            "<b>◉ System:</b>\n"
            "<blockquote>• <code>/clean</code> - Data cleanup wizard.\n"
            "• <code>/broadcast</code> [-f] - Broadcast to subscribers.\n"
            "• <code>/broadcast_groups</code> - Broadcast to groups.\n"
            "• <code>/restart</code> - Restart the bot.</blockquote>"
        )
        back_btn = InlineKeyboardMarkup([[InlineKeyboardButton('← Back', callback_data='help', style=enums.ButtonStyle.PRIMARY)]])
        await query.message.edit_media(InputMediaPhoto(PHOTO_URL, caption=txt), reply_markup=back_btn)

    # -------------------- USER GUIDE --------------------
    elif data == "help_guide":
        txt = (
            "<blockquote>"
            "⚙️ <b><u> Search Robot Guide</u></b> 💡\n\n"
            "To request a story, write the exact name.\n\n"
            "<b><i><u>✅ Correct examples:</u></i></b>\n"
            "Marvel Zombies Full Story\n"
            "Spider-Man Explainer\n\n"
            "<b><i><u>❌ Incorrect examples:</u></i></b>\n"
            "Do you have Marvel Zombies?\n"
            "Give me the link please\n\n"
            "<b>Got it? Try it now!</b>\n"
            "</blockquote>"
        )
        btn = [
            [InlineKeyboardButton('Go to Group 💬', url=REQUEST_GROUP, style=enums.ButtonStyle.SUCCESS)],
            [InlineKeyboardButton('← Back', callback_data='help', style=enums.ButtonStyle.PRIMARY)]
        ]
        await query.message.edit_media(InputMediaPhoto(PHOTO_URL, caption=txt), reply_markup=InlineKeyboardMarkup(btn))

    # -------------------- COPYRIGHT --------------------
    elif data == "help_copyright":
        txt = "<b>© Copyright</b>\n\nLinks are indexed automatically from Telegram channels. We do not host content ourselves."
        back_btn = InlineKeyboardMarkup([[InlineKeyboardButton('← Back', callback_data='help', style=enums.ButtonStyle.PRIMARY)]])
        await query.message.edit_media(InputMediaPhoto(PHOTO_URL, caption=txt), reply_markup=back_btn)

    # -------------------- GROUP SETTINGS --------------------
    elif data == "help_settings":
        txt = "<b>⚙️ Group Settings</b>\n\nSend <code>/settings</code> in the group to set:\n• Display mode (buttons/text)\n• Search trigger (!)\n• Number of results"
        back_btn = InlineKeyboardMarkup([[InlineKeyboardButton('← Back', callback_data='help', style=enums.ButtonStyle.PRIMARY)]])
        await query.message.edit_media(InputMediaPhoto(PHOTO_URL, caption=txt), reply_markup=back_btn)

    # -------------------- STATISTICS --------------------
    elif data == "help_stats":
        try:
            await query.message.edit_caption("⏳ **Calculating data...**")
        except:
            pass

        def get_size(bytes_val, suffix="B"):
            factor = 1024
            for unit in ["", "K", "M", "G", "T", "P"]:
                if bytes_val < factor:
                    return f"{bytes_val:.2f}{unit}{suffix}"
                bytes_val /= factor

        MAX_DB_SIZE = 536870912
        users = await db.users.count_documents({})
        files = await db.files.count_documents({})
        groups = await db.groups.count_documents({})

        try:
            db_stats = await db.users.database.command("dbstats")
            used_bytes = db_stats['storageSize']
            used_size = get_size(used_bytes)
            max_size = get_size(MAX_DB_SIZE)
            percentage = (used_bytes / MAX_DB_SIZE) * 100
            bar_len = 10
            filled_len = int(bar_len * percentage / 100)
            bar = '▓' * filled_len + '░' * (bar_len - filled_len)
            db_info = (
                f"🗄 <u>**Database Storage:**</u>\n"
                f"<blockquote>**★ Used:** `{used_size}`\n"
                f"**★ Out of:** `{max_size}`\n"
                f"★ **Status:** [{bar}] `{percentage:.2f}%`</blockquote>"
            )
        except Exception as e:
            db_info = f"❌ Unable to fetch technical data.\n`{e}`"

        txt = (
            f"📊 <u>**Bot Statistics:**</u>\n\n"
            f"🤖 <u>**Bot Status:**</u>\n"
            f"<blockquote>★ **Indexed Links:** `{files}`\n"
            f"★ **Users:** `{users}`\n"
            f"★ **Groups:** `{groups}`</blockquote>\n\n"
            f"{db_info}"
        )
        refresh_btn = InlineKeyboardMarkup([
            [InlineKeyboardButton('← Back', callback_data='help', style=enums.ButtonStyle.PRIMARY),
             InlineKeyboardButton('↻ Refresh', callback_data='help_stats', style=enums.ButtonStyle.SUCCESS)]
        ])
        await query.message.edit_media(InputMediaPhoto(PHOTO_URL, caption=txt), reply_markup=refresh_btn)

    # -------------------- ABOUT --------------------
    elif data == "about":
        bot_name = client.me.first_name
        bot_username = client.me.username
        bot_mention = f"[{bot_name}](https://t.me/{bot_username})"
        txt = (
            "<blockquote><b>╔════❰ About The Bot ❱═❍⊱❁۪۪</b>\n"
            "<b>║╭━━━━━━━━━━━━━━━➣</b>\n"
            f"<b>║┣⪼ 🤖 Bot : {bot_mention}</b>\n"
            "<b>║┣⪼ 👦 Creator : @TJ_Bots_Admin</b>\n"
            f"<b>║┣⪼ 🤖 Update : <a href='https://t.me/{UPDATE_CHANNEL}'>Update Channel</a></b>\n"
            "<b>║┣⪼ 🗣️ Language : [Python](https://www.python.org/)</b>\n"
            "<b>║┣⪼ 📚 Library : [Pyrogram](https://docs.pyrogram.org/)</b>\n"
            f"<b>║┣⪼ &lt;/&gt; Source : <a href='https://github.com/Tj-Bots/Auto-Filter'>GitHub</a></b>\n"
            "<b>║╰━━━━━━━━━━━━━━━➣</b>\n"
            "<b>╚══════════════════❍⊱❁۪۪</b></blockquote>"
        )
        btn = [
            [InlineKeyboardButton('🐙 Source Code 🐙', url='https://github.com/Tj-Bots/Auto-Filter', style=enums.ButtonStyle.SUCCESS)],
            [InlineKeyboardButton('← Back', callback_data='home', style=enums.ButtonStyle.PRIMARY),
             InlineKeyboardButton('✘ Close', callback_data='closea', style=enums.ButtonStyle.DANGER)]
        ]
        await query.message.edit_media(InputMediaPhoto(PHOTO_URL, caption=txt), reply_markup=InlineKeyboardMarkup(btn))

    # -------------------- TIKTOK HELP --------------------
    elif data == "help_d":
        txt = (
            "📥 <b><u>TikTok Downloader:</u></b>\n\n"
            "<b>◉ Command:</b>\n<blockquote>/d</blockquote>\n\n"
            "<b>◉ How to use:</b>\n<blockquote>Send the command with a link or reply to a link.</blockquote>"
        )
        back_btn = InlineKeyboardMarkup([[InlineKeyboardButton('← Back', callback_data='help', style=enums.ButtonStyle.PRIMARY)]])
        await query.message.edit_media(InputMediaPhoto(PHOTO_URL, caption=txt), reply_markup=back_btn)

    # -------------------- TELEGRAPH HELP --------------------
    elif data == "help_telegraph":
        txt = (
            "📤 <b><u>Upload Images to i.ibb.co</u></b> 🖼️\n\n"
            "<b>◉ Command:</b>\n<blockquote>/telegraph</blockquote>\n\n"
            "<b>◉ How to use:</b>\n<blockquote>Reply to an image with the command.</blockquote>"
        )
        back_btn = InlineKeyboardMarkup([[InlineKeyboardButton('← Back', callback_data='help', style=enums.ButtonStyle.PRIMARY)]])
        await query.message.edit_media(InputMediaPhoto(PHOTO_URL, caption=txt), reply_markup=back_btn)

    # -------------------- VIDEO TOOLS HELP --------------------
    elif data == "help_exthumb":
        txt = (
            "🔧 <b><i>Video Tools:</i></b>\n\n"
            "ℹ️ <b><u>Video Info:</u></b>\n"
            "<blockquote>/mediainfo</blockquote>\n\n"
            "🖼️ <b><u>Extract Thumbnail:</u></b>\n"
            "<blockquote>/extract_thumbnail</blockquote>\n\n"
            "<b>How to use:</b>\n<blockquote>Reply to a video/file with the command.</blockquote>"
        )
        back_btn = InlineKeyboardMarkup([[InlineKeyboardButton('← Back', callback_data='help', style=enums.ButtonStyle.PRIMARY)]])
        await query.message.edit_media(InputMediaPhoto(PHOTO_URL, caption=txt), reply_markup=back_btn)

    # -------------------- CLOSE / NOOP --------------------
    elif data == "closea":
        try:
            await query.message.delete()
            await query.message.reply_to_message.delete()
        except:
            pass

    elif data == "noop":
        await query.answer()
