import os
import asyncio
from dotenv import load_dotenv
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

# Load environment variables from .env locally or Render environment
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
MODERATOR_CHAT_ID = int(os.getenv("MODERATOR_CHAT_ID", "0"))

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is missing!")

# Initialize Bot and Dispatcher
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Get port from Render environment variables (default to 8080 for local testing)
PORT = int(os.environ.get("PORT", 8080))
WEBHOOK_PATH = f"/{BOT_TOKEN}"  # Use your bot token as a secure path suffix
# On Render, your external URL will look like: https://your-service-name.onrender.com
WEBHOOK_URL = f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'localhost')}{WEBHOOK_PATH}"

async def on_startup(bot: Bot):
    # Set the webhook URL on Telegram's side when the app starts
    await bot.set_webhook(WEBHOOK_URL)

async def main():
    # Register startup hook
    dp.startup.register(on_startup)

    # Create an aiohttp web application
    app = web.Application()

    # Create webhook request handler
    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
    )
    # Register webhook handler route on the aiohttp app
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)

    # Setup application bindings
    setup_application(app, dp, bot=bot)

    # Start the web app on 0.0.0.0 and the assigned PORT
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    
    # Keep the application running
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
