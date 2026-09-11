import asyncio
import random
import string
import pytz
import datetime
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, InputMediaPhoto
import config
from database import db, get_shortlink
from .utils import get_readable_size

# ------------------------------------------------------------ #
#                        FILE SEND HELPER                       #
# ------------------------------------------------------------ #
async def send_file_with_fallback(client, chat_id, file_data, reply_to_id=None):
    """Try to copy message, fallback to send_video or send_document"""
    try:
        await client.copy_message(
            chat_id=chat_id,
            from_chat_id=file_data['chat_id'],
            message_id=file_data['message_id'],
            caption=None,
            reply_to_message_id=reply_to_id
        )
        return True
    except:
        file_id = file_data.get('file_id')
        if not file_id:
            return False

        file_name = file_data.get('file_name', '')
        file_size = get_readable_size(file_data.get('file_size', 0))
        fallback_caption = f"**{file_name}**\n\n**💾 Size: {file_size}**"

        try:
            await client.send_video(
                chat_id=chat_id,
                video=file_id,
                caption=fallback_caption,
                reply_to_message_id=reply_to_id
            )
            return True
        except:
            try:
                await client.send_document(
                    chat_id=chat_id,
                    document=file_id,
                    caption=fallback_caption,
                    reply_to_message_id=reply_to_id
                )
                return True
            except:
                return False

# ------------------------------------------------------------ #
#                           START CMD                           #
# ------------------------------------------------------------ #
@Client.on_message(filters.command("start"))
async def start_command(client, message):
    if message.chat.type == enums.ChatType.PRIVATE:
        user_id = message.from_user.id
        param = message.command[1] if len(message.command) > 1 else ""

        # ---------------- TOKEN VERIFICATION RETURN HANDLER ---------------- #
        if param.startswith("notcopy_") or param.startswith("sendall_"):
            try:
                _, u_id, verify_id, file_db_id = param.split("_", 3)
                
                if int(u_id) != user_id:
                    return await message.reply_text("❌ Invalid link ownership.")

                verify_info = await db.get_verify_id_info(user_id, verify_id)
                if not verify_info:
                    return await message.reply_text("❌ **Invalid or Expired Link!** Please try again.")

                if verify_info.get("verified"):
                    return await message.reply_text("⚠️ **This link has already been used.**")

                # Mark Token as Verified
                await db.update_verify_id_info(user_id, verify_id, {"verified": True})

                # Update verification dates according to status
                ist_tz = pytz.timezone('Asia/Kolkata')
                now = datetime.datetime.now(tz=ist_tz)

                is_v1 = await db.is_user_verified(user_id)
                is_v2 = await db.user_verified(user_id)

                if not is_v1:
                    await db.update_notcopy_user(user_id, {"last_verified": now})
                    await message.reply_text("✅ **1st Verification Successful!**")
                elif not is_v2:
                    await db.update_notcopy_user(user_id, {"second_time_verified": now})
                    await message.reply_text("✅ **2nd Verification Successful!**")
                else:
                    await db.update_notcopy_user(user_id, {"third_time_verified": now})
                    await message.reply_text("✅ **3rd Verification Successful!**")

                # Send File After Verification
                file_data = await db.get_file(file_db_id)
                if file_data:
                    await send_file_with_fallback(client, message.chat.id, file_data, message.id)
                return

            except Exception as e:
                return await message.reply_text("❌ Verification Failed. Unexpected Error.")

        # ---------------- FILE ACCESS WITH VERIFICATION CHECK ---------------- #
        if param:
            file_db_id = param

            # Force Subscription Check
            if config.AUTH_CHANNEL_FORCE:
                is_subbed = True
                try:
                    await client.get_chat_member(config.UPDATE_CHANNEL, user_id)
                except:
                    is_subbed = False

                if not is_subbed:
                    btn = [
                        [InlineKeyboardButton('📣 Join Channel', url=f'https://t.me/{config.UPDATE_CHANNEL}')],
                        [InlineKeyboardButton('↻ Try Again', callback_data=f"checksub_{file_db_id}")]
                    ]
                    return await message.reply_text(
                        "**To use this bot you must subscribe to its update channel! 🫰**",
                        reply_markup=InlineKeyboardMarkup(btn),
                        quote=True
                    )

            # Verification Gateway Check
            if config.IS_VERIFY and not await db.has_premium_access(user_id):
                try:
                    user_verified = await db.is_user_verified(user_id)
                    is_second_shortener = await db.use_second_shortener(user_id, config.TWO_VERIFY_GAP)
                    is_third_shortener = await db.use_third_shortener(user_id, config.THREE_VERIFY_GAP)

                    if not user_verified or is_second_shortener or is_third_shortener:
                        verify_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=7))
                        await db.create_verify_id(user_id, verify_id)

                        deep_link = f"https://telegram.me/{client.me.username}?start=notcopy_{user_id}_{verify_id}_{file_db_id}"
                        verify_url = await get_shortlink(deep_link, grp_id=None, is_second_shortener=is_second_shortener, is_third_shortener=is_third_shortener)

                        if is_third_shortener:
                            howtodownload = config.TUTORIAL_3
                        else:
                            howtodownload = config.TUTORIAL_2 if is_second_shortener else config.TUTORIAL

                        buttons = [
                            [InlineKeyboardButton(text="♻️ ᴄʟɪᴄᴋ ʜᴇʀᴇ ᴛᴏ ᴠᴇʀɪꜰʏ ♻️", url=verify_url)],
                            [InlineKeyboardButton(text="⁉️ ʜᴏᴡ ᴛᴏ ᴠᴇʀɪꜰʏ ⁉️", url=howtodownload)]
                        ]
                        reply_markup = InlineKeyboardMarkup(buttons)

                        if await db.user_verified(user_id):
                            msg_text = config.THIRDT_VERIFICATION_TEXT
                        else:
                            msg_text = config.SECOND_VERIFICATION_TEXT if is_second_shortener else config.VERIFICATION_TEXT

                        n = await message.reply_text(
                            text=msg_text.format(message.from_user.mention),
                            reply_markup=reply_markup,
                            parse_mode=enums.ParseMode.HTML,
                            quote=True
                        )
                        await asyncio.sleep(300)
                        await n.delete()
                        await message.delete()
                        return

                except Exception as e:
                    print(f"Error In Verification: {e}")

            # Send file directly if already verified
            file_data = await db.get_file(file_db_id)
            if file_data:
                success = await send_file_with_fallback(client, message.chat.id, file_data, message.id)
                if not success:
                    await message.reply("❌ The file was deleted or inaccessible.", quote=True)
            return

        # Normal Start Message
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
        await message.reply("Hey! I'm ready to search for movies 🎬", quote=True)

# ------------------------------------------------------------ #
#                      GROUP ADD HANDLER                        #
# ------------------------------------------------------------ #
@Client.on_message(filters.new_chat_members)
async def added_to_group(client, message):
    for member in message.new_chat_members:
        if member.id == client.me.id:
            await message.reply(
                "Thanks for adding me! 🎬\n"
                "Send the name of the movie/series you want to search for.",
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
        [InlineKeyboardButton('✇ Group ✇', url=config.REQUEST_GROUP, style=enums.ButtonStyle.SUCCESS),
         InlineKeyboardButton('✇ Updates ✇', url=f'https://t.me/{config.UPDATE_CHANNEL}', style=enums.ButtonStyle.SUCCESS)],
        [InlineKeyboardButton('〄 Help 〄', callback_data='help', style=enums.ButtonStyle.PRIMARY),
         InlineKeyboardButton('⍟ About ⍟', callback_data='about', style=enums.ButtonStyle.PRIMARY)],
        [InlineKeyboardButton('⇋ Add to Group ⇋', url=f"http://t.me/{client.me.username}?startgroup&admin=delete_messages", style=enums.ButtonStyle.SUCCESS)]
    ]

    txt = (
        f"**Hey {user_mention} 👋**\n"
        f"**Welcome to {bot_mention}** 😎\n\n"
        "**I am an innovative movie and series search engine,**\n"
        "<b>My job is to search for movies in groups,\n"
        "Add me to your group and I'll take it from here.</b> ☄️\n\n"
        "<blockquote>**👨🏼‍💻 Lead Developer: @TJ_Bots_Admin**</blockquote>"
    )

    if is_edit:
        await message.edit_media(InputMediaPhoto(config.PHOTO_URL, caption=txt), reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await message.reply_photo(config.PHOTO_URL, caption=txt, reply_markup=InlineKeyboardMarkup(buttons), quote=True)

# ------------------------------------------------------------ #
#                        CALLBACK HANDLER                       #
# ------------------------------------------------------------ #
@Client.on_callback_query()
async def callback_handler(client, query: CallbackQuery):
    data = query.data
    user_id = query.from_user.id

    if data.startswith("checksub_"):
        file_db_id = data.split("_")[1]
        is_subbed = True

        if config.AUTH_CHANNEL_FORCE:
            try:
                await client.get_chat_member(config.UPDATE_CHANNEL, user_id)
            except:
                is_subbed = False

        if not is_subbed:
            return await query.answer("❌ You must join the update channel first!", show_alert=True)

        file_data = await db.get_file(file_db_id)
        if file_data:
            reply_to = query.message.reply_to_message.id if query.message.reply_to_message else None
            success = await send_file_with_fallback(client, query.message.chat.id, file_data, reply_to)
            if success:
                await query.message.delete()
            else:
                await query.answer("❌ File not found or inaccessible.", show_alert=True)
        else:
            await query.answer("❌ File not found in database.", show_alert=True)
        return

    if data == "help_admin" and user_id not in config.ADMINS:
        return await query.answer("⛔ Admins only.", show_alert=True)

    if data not in ["closea", "noop", "help_stats"]:
        try:
            await query.message.edit_media(InputMediaPhoto(config.PHOTO_URL, caption=""), reply_markup=None)
            await asyncio.sleep(0.1)
        except:
            pass

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
        if user_id in config.ADMINS:
            btns.insert(0, [InlineKeyboardButton('👮‍♂️ Admin Commands 👮‍♂️', callback_data='help_admin', style=enums.ButtonStyle.DANGER)])

        await query.message.edit_media(
            InputMediaPhoto(config.PHOTO_URL, caption=f"<b>Hey {user_mention},\nHere you can get help for all my commands.</b>"),
            reply_markup=InlineKeyboardMarkup(btns)
        )

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
        await query.message.edit_media(InputMediaPhoto(config.PHOTO_URL, caption=txt), reply_markup=back_btn)

    elif data == "help_admin":
        txt = (
            "<b><u>Admin Control Panel:</u></b>\n\n"
            "<b>◉ Content Management:</b>\n"
            "<blockquote>• <code>/index</code> [link] - [start] - Add files from a channel (by range).\n"
            "• <code>/newindex</code> [ID] - Track new content in a channel.\n"
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
        await query.message.edit_media(InputMediaPhoto(config.PHOTO_URL, caption=txt), reply_markup=back_btn)

    elif data == "help_guide":
        txt = (
            "<blockquote>"
            "⚙️ <b><u> Search Robot Guide</u></b> 💡\n\n"
            "To request a movie or series, write the exact name.\n\n"
            "<b><i><u>✅ Correct examples:</u></i></b>\n"
            "Ashamti\n"
            "Fast and Furious\n\n"
            "<b><i><u>❌ Incorrect examples:</u></i></b>\n"
            "Do you have Harry Potter?\n"
            "Can I get Harry Potter?\n\n"
            "<b>Got it? Try it now!</b>\n"
            "</blockquote>"
        )
        btn = [
            [InlineKeyboardButton('Go to Group 💬', url=config.REQUEST_GROUP, style=enums.ButtonStyle.SUCCESS)],
            [InlineKeyboardButton('← Back', callback_data='help', style=enums.ButtonStyle.PRIMARY)]
        ]
        await query.message.edit_media(InputMediaPhoto(config.PHOTO_URL, caption=txt), reply_markup=InlineKeyboardMarkup(btn))

    elif data == "help_copyright":
        txt = "<b>© Copyright</b>\n\nFiles are collected automatically from Telegram. We do not upload content ourselves."
        back_btn = InlineKeyboardMarkup([[InlineKeyboardButton('← Back', callback_data='help', style=enums.ButtonStyle.PRIMARY)]])
        await query.message.edit_media(InputMediaPhoto(config.PHOTO_URL, caption=txt), reply_markup=back_btn)

    elif data == "help_settings":
        txt = "<b>⚙️ Group Settings</b>\n\nSend <code>/settings</code> in the group to set:\n• Display mode (buttons/text)\n• Search trigger (!)\n• Number of results"
        back_btn = InlineKeyboardMarkup([[InlineKeyboardButton('← Back', callback_data='help', style=enums.ButtonStyle.PRIMARY)]])
        await query.message.edit_media(InputMediaPhoto(config.PHOTO_URL, caption=txt), reply_markup=back_btn)

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
            f"<blockquote>★ **Files:** `{files}`\n"
            f"★ **Users:** `{users}`\n"
            f"★ **Groups:** `{groups}`</blockquote>\n\n"
            f"{db_info}"
        )
        refresh_btn = InlineKeyboardMarkup([
            [InlineKeyboardButton('← Back', callback_data='help', style=enums.ButtonStyle.PRIMARY),
             InlineKeyboardButton('↻ Refresh', callback_data='help_stats', style=enums.ButtonStyle.SUCCESS)]
        ])
        await query.message.edit_media(InputMediaPhoto(config.PHOTO_URL, caption=txt), reply_markup=refresh_btn)

    elif data == "about":
        bot_name = client.me.first_name
        bot_username = client.me.username
        bot_mention = f"[{bot_name}](https://t.me/{bot_username})"
        txt = (
            "<blockquote><b>╔════❰ About The Bot ❱═❍⊱❁۪۪</b>\n"
            "<b>║╭━━━━━━━━━━━━━━━➣</b>\n"
            f"<b>║┣⪼ 🤖 Bot : {bot_mention}</b>\n"
            "<b>║┣⪼ 👦 Creator : @TJ_Bots_Admin</b>\n"
            f"<b>║┣⪼ 🤖 Update : <a href='https://t.me/{config.UPDATE_CHANNEL}'>Update Channel</a></b>\n"
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
        await query.message.edit_media(InputMediaPhoto(config.PHOTO_URL, caption=txt), reply_markup=InlineKeyboardMarkup(btn))

    elif data == "help_d":
        txt = (
            "📥 <b><u>TikTok Downloader:</u></b>\n\n"
            "<b>◉ Command:</b>\n<blockquote>/d</blockquote>\n\n"
            "<b>◉ How to use:</b>\n<blockquote>Send the command with a link or reply to a link.</blockquote>"
        )
        back_btn = InlineKeyboardMarkup([[InlineKeyboardButton('← Back', callback_data='help', style=enums.ButtonStyle.PRIMARY)]])
        await query.message.edit_media(InputMediaPhoto(config.PHOTO_URL, caption=txt), reply_markup=back_btn)

    elif data == "help_telegraph":
        txt = (
            "📤 <b><u>Upload Images to i.ibb.co</u></b> 🖼️\n\n"
            "<b>◉ Command:</b>\n<blockquote>/telegraph</blockquote>\n\n"
            "<b>◉ How to use:</b>\n<blockquote>Reply to an image with the command.</blockquote>"
        )
        back_btn = InlineKeyboardMarkup([[InlineKeyboardButton('← Back', callback_data='help', style=enums.ButtonStyle.PRIMARY)]])
        await query.message.edit_media(InputMediaPhoto(config.PHOTO_URL, caption=txt), reply_markup=back_btn)

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
        await query.message.edit_media(InputMediaPhoto(config.PHOTO_URL, caption=txt), reply_markup=back_btn)

    elif data == "closea":
        try:
            await query.message.delete()
            await query.message.reply_to_message.delete()
        except:
            pass

    elif data == "noop":
        await query.answer()
