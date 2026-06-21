import logging
import asyncio
import os
import threading
from http.server import SimpleHTTPRequestHandler, HTTPServer
from pyrogram import Client, idle
from config import API_ID, API_HASH, BOT_TOKEN, LOG_CHANNEL
from database import db

# Logging configuration
logging.basicConfig(
    level=logging.ERROR,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Render Port Handler (Fake HTTP Server for Render)
def run_port_server():
    # Render automatically provides a PORT environment variable
    port = int(os.environ.get("PORT", 8080))
    server_address = ("", port)
    
    class SimpleHandler(SimpleHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Bot is alive and running!")

    httpd = HTTPServer(server_address, SimpleHandler)
    print(f"🌐 Fake server started on port {port} for Render health check.")
    httpd.serve_forever()

# Pyrogram Client Setup
app = Client(
    "TjBot_Session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    plugins=dict(root="Tj_Bots") 
)

async def start_bot():
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
    except: 
        pass

    print("✅ Bot is online! Go test it out.")
    await idle()
    await app.stop()

if __name__ == "__main__":
    # 1. Start the Port Server in a background thread so it doesn't block the bot
    port_thread = threading.Thread(target=run_port_server, daemon=True)
    port_thread.start()

    # 2. Run the main Pyrogram Bot
    app.run(start_bot())
