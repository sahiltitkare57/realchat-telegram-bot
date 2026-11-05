import os
import asyncio
import sqlite3
from dotenv import load_dotenv
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

# Load environment variables
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
MODERATOR_CHAT_ID = int(os.getenv("MODERATOR_CHAT_ID", "0"))

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is missing!")

# Initialize Bot and Dispatcher
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Database Setup
def init_db():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT,
            age INTEGER,
            bio TEXT,
            city TEXT,
            video_file_id TEXT,
            status TEXT DEFAULT 'pending'
        )
    """)
    conn.commit()
    conn.close()

init_db()

# /start Command Handler
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        await message.answer(
            "Namaskar! RealChat_Bot madhye tumche swagat ahe.\n\n"
            "Ya bot madhye yenyasathi tumhi 18+ asne garajeche ahe ani mandatory video verification karave lagel.\n\n"
            "Tumche naav (Full Name) pathva:"
        )
    else:
        status = row[0]
        if status == 'approved':
            await message.answer("Tumche profile already verified ahe! Profiles browse karnyasathi /browse vapra.")
        elif status == 'pending':
            await message.answer("Tumchi video verification ani profile sadhya moderation sathi pending ahe.")
        else:
            await message.answer("Tumche profile reject zale ahe.")

# /browse Command Handler
@dp.message(Command("browse"))
async def cmd_browse(message: types.Message):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT full_name, age, bio, city FROM users WHERE status = 'approved'")
    users = cursor.fetchall()
    conn.close()

    if not users:
        await message.answer("Sadhya kontehi approved profiles uplabdh nahiyet. Kahi welane parat try kara!")
        return

    for u in users:
        text = f"Naav: {u[0]}, Vay: {u[1]}\nCity: {u[3]}\nBio: {u[2]}"
        await message.answer(text)

# Webhook configuration
PORT = int(os.environ.get("PORT", 8080))
WEBHOOK_PATH = f"/{BOT_TOKEN}"
WEBHOOK_URL = f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'localhost')}{WEBHOOK_PATH}"

async def on_startup(bot: Bot):
    await bot.set_webhook(WEBHOOK_URL)

async def main():
    dp.startup.register(on_startup)
    app = web.Application()
    webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
