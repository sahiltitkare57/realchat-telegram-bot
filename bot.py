import os
import asyncio
import sqlite3
from dotenv import load_dotenv
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder
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

# Define FSM States for Registration
class Registration(StatesGroup):
    full_name = State()
    age = State()
    city = State()
    bio = State()
    video_verification = State()

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
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        await state.set_state(Registration.full_name)
        await message.answer(
            "Welcome to RealChat_Bot!\n\n"
            "To use this bot, you must be 18+ and complete a mandatory video verification.\n\n"
            "Please send your Full Name:"
        )
    else:
        status = row[0]
        if status == 'approved':
            await message.answer("Your profile is already verified! Use /browse to check out profiles.")
        elif status == 'pending':
            await message.answer("Your video verification and profile are currently pending moderator approval.")
        else:
            await message.answer("Your profile verification was rejected.")

# Step 1: Capture Full Name
@dp.message(Registration.full_name, F.text)
async def process_full_name(message: types.Message, state: FSMContext):
    await state.update_data(full_name=message.text)
    await state.set_state(Registration.age)
    await message.answer("Great! Now, please enter your Age (must be 18 or older):")

# Step 2: Capture Age
@dp.message(Registration.age, F.text)
async def process_age(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Please enter a valid number for your age.")
        return
    
    age = int(message.text)
    if age < 18:
        await message.answer("Sorry, you must be 18 or older to use this bot.")
        await state.clear()
        return

    await state.update_data(age=age)
    await state.set_state(Registration.city)
    await message.answer("Which city are you located in?")

# Step 3: Capture City
@dp.message(Registration.city, F.text)
async def process_city(message: types.Message, state: FSMContext):
    await state.update_data(city=message.text)
    await state.set_state(Registration.bio)
    await message.answer("Write a short Bio about yourself:")

# Step 4: Capture Bio
@dp.message(Registration.bio, F.text)
async def process_bio(message: types.Message, state: FSMContext):
    await state.update_data(bio=message.text)
    await state.set_state(Registration.video_verification)
    await message.answer(
        "Almost done! Now please send a **Video Message** (or video upload) "
        "stating your name and age for verification."
    )

# Step 5: Capture Video Verification and Send to Moderator
@dp.message(Registration.video_verification, F.video | F.video_note | F.document)
async def process_video(message: types.Message, state: FSMContext):
    video_file_id = None
    if message.video:
        video_file_id = message.video.file_id
    elif message.video_note:
        video_file_id = message.video_note.file_id
    elif message.document:
        video_file_id = message.document.file_id

    if not video_file_id:
        await message.answer("Please send a valid video file or video note.")
        return

    data = await state.get_data()
    user_id = message.from_user.id

    # Save to SQLite Database as 'pending'
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO users (user_id, full_name, age, bio, city, video_file_id, status)
        VALUES (?, ?, ?, ?, ?, ?, 'pending')
    """, (user_id, data['full_name'], data['age'], data['bio'], data['city'], video_file_id))
    conn.commit()
    conn.close()

    await state.clear()
    await message.answer(
        "Thank you! Your registration and video verification have been submitted "
        "to moderators. You will be notified once approved."
    )

    # Send to Moderator Chat with Approve / Reject Buttons
    if MODERATOR_CHAT_ID != 0:
        builder = InlineKeyboardBuilder()
        builder.button(text="✅ Approve", callback_data=f"approve_{user_id}")
        builder.button(text="❌ Reject", callback_data=f"reject_{user_id}")
        builder.adjust(2)

        caption = (
            f"🔔 New Verification Request!\n\n"
            f"👤 Name: {data['full_name']}\n"
            f"🎂 Age: {data['age']}\n"
            f"📍 City: {data['city']}\n"
            f"📝 Bio: {data['bio']}\n"
            f"🆔 User ID: {user_id}"
        )

        try:
            if message.video:
                await bot.send_video(MODERATOR_CHAT_ID, video_file_id, caption=caption, reply_markup=builder.as_markup())
            elif message.video_note:
                await bot.send_video_note(MODERATOR_CHAT_ID, video_file_id)
                await bot.send_message(MODERATOR_CHAT_ID, caption, reply_markup=builder.as_markup())
            elif message.document:
                await bot.send_document(MODERATOR_CHAT_ID, video_file_id, caption=caption, reply_markup=builder.as_markup())
        except Exception as e:
            print(f"Failed to notify moderator: {e}")

# Admin Callback Handler (Approve / Reject)
@dp.callback_query(F.data.startswith("approve_") | F.data.startswith("reject_"))
async def process_moderation(callback: types.CallbackQuery):
    action, user_id_str = callback.data.split("_")
    target_user_id = int(user_id_str)

    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()

    if action == "approve":
        cursor.execute("UPDATE users SET status = 'approved' WHERE user_id = ?", (target_user_id,))
        conn.commit()
        conn.close()

        await callback.message.edit_caption(caption=callback.message.caption + "\n\n✅ **STATUS: APPROVED**", parse_mode="Markdown")
        await callback.answer("Profile approved successfully!")

        try:
            await bot.send_message(target_user_id, "🎉 Your profile has been approved by the moderator! You can now use /browse to check out profiles.")
        except Exception:
            pass

    elif action == "reject":
        cursor.execute("UPDATE users SET status = 'rejected' WHERE user_id = ?", (target_user_id,))
        conn.commit()
        conn.close()

        await callback.message.edit_caption(caption=callback.message.caption + "\n\n❌ **STATUS: REJECTED**", parse_mode="Markdown")
        await callback.answer("Profile rejected.")

        try:
            await bot.send_message(target_user_id, "❌ Unfortunately, your profile verification was rejected by moderators.")
        except Exception:
            pass

# /browse Command Handler
@dp.message(Command("browse"))
async def cmd_browse(message: types.Message):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT full_name, age, bio, city FROM users WHERE status = 'approved'")
    users = cursor.fetchall()
    conn.close()

    if not users:
        await message.answer("No approved profiles available right now. Check back later!")
        return

    for u in users:
        text = f"Name: {u[0]}, Age: {u[1]}\nCity: {u[3]}\nBio: {u[2]}"
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
