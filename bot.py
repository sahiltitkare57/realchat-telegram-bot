import os
from aiohttp import web
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

# Get port from Render environment variables (default to 8080 for local testing)
PORT = int(os.environ.get("PORT", 8080))
WEBHOOK_PATH = f"/{BOT_TOKEN}"  # Use your bot token as a secure path suffix
# On Render, your external URL will look like: https://your-service-name.onrender.com
WEBHOOK_URL = f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'localhost')}{WEBHOOK_PATH}"

async def on_startup(bot):
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
    import asyncio
    asyncio.run(main())
