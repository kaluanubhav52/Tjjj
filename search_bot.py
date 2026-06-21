import logging
import asyncio
import os
from aiohttp import web
from pyrogram import Client, idle
from config import API_ID, API_HASH, BOT_TOKEN, LOG_CHANNEL
from database import db

# Logging configuration
logging.basicConfig(
    level=logging.INFO, # Changed to INFO to track server initialization
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 1. Advanced Async HTTP Server for Render Health Checks
async def handle_health_check(request):
    return web.Response(text="Bot is perfectly healthy and running! 🚀", status=200)

async def start_port_server():
    app = web.Application()
    app.router.add_get('/', handle_health_check)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    # Render assigns a dynamic port via environment variable
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    
    await site.start()
    logger.info(f"🌐 Advanced Async Web Server started on port {port}")
    return runner

# 2. Pyrogram Client Setup
app = Client(
    "TjBot_Session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    plugins=dict(root="Tj_Bots") 
)

async def main():
    # A. Start the web server first so Render sees the port immediately active
    web_runner = await start_port_server()

    print("🤖 Bot is waking up...")
    await app.start()
    await db.init_database(app)
    
    # Handle restart message if exists
    if os.path.exists("restart.txt"):
        try:
            with open("restart.txt", "r") as f:
                content = f.read().split()
                if len(content) == 2:
                    chat_id, msg_id = int(content[0]), int(content[1])
                    await app.edit_message_text(chat_id, msg_id, "Bot is back online! ✅")
            os.remove("restart.txt")
        except Exception as e:
            print(f"Error editing restart message: {e}")
            
    # Send start log to channel
    try:
        me = await app.get_me()
        await app.send_message(
            LOG_CHANNEL,
            f"#BotStarted\n✅ **Bot is up and running!**\n@{me.username}"
        )
    except Exception as e:
        logger.error(f"Failed to send startup log: {e}")

    print("✅ Bot is online! Go test it out.")
    
    # B. Keep bot running smoothly
    await idle()
    
    # C. Graceful Shutdown Sequence (If server stops)
    print("👋 Shutting down safely...")
    await app.stop()
    await web_runner.cleanup() # Safely close the port server
    print("🛑 Bot stopped successfully.")

if __name__ == "__main__":
    # Standard python loop execution for modern async code
    asyncio.run(main())
