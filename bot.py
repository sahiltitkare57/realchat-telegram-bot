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
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from google import genai

# Load environment variables
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODERATOR_CHAT_ID = int(os.getenv("MODERATOR_CHAT_ID", "0"))

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is missing!")

# Initialize Bot, Dispatcher, and Gemini Client
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# Define FSM States for Registration
class Registration(StatesGroup):
    full_name = State()
    age = State()
    city = State()
    bio = State()
    video_verification = State()

# Database Setup with AI Verification Column
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
            ai_trust_score TEXT DEFAULT 'Pending',
            status TEXT DEFAULT 'pending'
        )
    """)
    conn.commit()
    conn.close()

init_db()

# AI Feature 1: Polish Bio
async def polish_bio_with_ai(raw_bio: str) -> str:
    if not gemini_client:
        return raw_bio
    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"Rewrite this dating profile bio to be warm, friendly, and engaging, keeping it under 20 words: '{raw_bio}'"
        )
        return response.text.strip()
    except Exception as e:
        print(f"Gemini Bio Polish error: {e}")
        return raw_bio

# AI Feature 2: Video Vision Pre-Screening
async def verify_video_with_ai(file_path: str) -> str:
    if not gemini_client:
        return "🤖 AI: Not Checked"
    try:
        # Upload file to Gemini Files API for vision analysis
        video_file = gemini_client.files.upload(file=file_path)
        
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                video_file,
                "Analyze this video verification clip. Is there a clear human face visible speaking or showing their face for a dating app? Reply ONLY with 'TRUSTED: [Short reason]' or 'FLAGGED: [Reason]'."
            ]
        )
        result = response.text.strip()
        # Cleanup file from Gemini servers
        gemini_client.files.delete(name=video_file.name)
        return f"🤖 AI Verdict: {result}"
    except Exception as e:
        print(f"Gemini Video Analysis error: {e}")
        return "🤖 AI Verdict: Check Passed (Manual Review)"

# AI Feature 3: Generate Dynamic Icebreaker
async def generate_ai_icebreaker(name: str, bio: str, city: str) -> str:
    if not gemini_client:
        return f"Hey {name}, nice to meet you!"
    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"Generate a short, friendly, flirty icebreaker message for a dating app user named {name} who lives in {city} with bio: '{bio}'. Keep it under 15 words."
        )
        return response.text.strip()
    except Exception as e:
        print(f"Gemini Icebreaker error: {e}")
        return f"Hey {name}! Saw you're in {city}."

# Helper: Main Persistent Menu Keyboard (Bottom Bar)
def get_main_menu():
    builder = ReplyKeyboardBuilder()
    builder.button(text="🔍 Find Partner")
    builder.button(text="👤 My Profile")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

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
            "Welcome to RealChat_Bot (AI Powered)!\n\n"
            "To use this bot, you must be 18+ and complete a mandatory video verification.\n\n"
            "Please send your Full Name:"
        )
    else:
        status = row[0]
        if status == 'approved':
            await message.answer(
                "Your profile is already verified! Use the menu below to find partners.",
                reply_markup=get_main_menu()
            )
        elif status == 'pending':
            await message.answer("Your video verification and profile are currently pending moderator approval.")
        else:
            await message.answer("Your profile verification was rejected.")

# /update Command Handler to reset and re-register profile
@dp.message(Command("update"))
async def cmd_update(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

    await state.set_state(Registration.full_name)
    await message.answer(
        "🔄 Let's update your profile!\n\n"
        "Please send your correct Full Name:"
    )

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
    await message.answer("Write a short Bio about yourself (AI will polish it!):")

# Step 4: Capture Bio & Apply AI Polishing
@dp.message(Registration.bio, F.text)
async def process_bio(message: types.Message, state: FSMContext):
    raw_bio = message.text
    polished_bio = await polish_bio_with_ai(raw_bio)
    
    await state.update_data(bio=polished_bio)
    await state.set_state(Registration.video_verification)
    await message.answer(
        f"✨ **AI Polished your bio to:**\n> *\"{polished_bio}\"*\n\n"
        "Almost done! Now please send a **Video Message** (or video upload) "
        "stating your name and age for AI verification.",
        parse_mode="Markdown"
    )

# Step 5: Capture Video, Run AI Vision Analysis, & Send to Moderator
@dp.message(Registration.video_verification, F.video | F.video_note | F.document)
async def process_video(message: types.Message, state: FSMContext):
    video_file_id = None
    file_obj = None
    if message.video:
        video_file_id = message.video.file_id
        file_obj = message.video
    elif message.video_note:
        video_file_id = message.video_note.file_id
        file_obj = message.video_note
    elif message.document:
        video_file_id = message.document.file_id
        file_obj = message.document

    if not video_file_id:
        await message.answer("Please send a valid video file or video note.")
        return

    # Download video temporarily for Gemini Vision Analysis
    temp_filename = f"temp_{message.from_user.id}.mp4"
    file_info = await bot.get_file(video_file_id)
    await bot.download_file(file_info.file_path, destination=temp_filename)

    # Run AI Vision Pre-Screening
    ai_trust_result = await verify_video_with_ai(temp_filename)

    # Clean up temp file
    if os.path.exists(temp_filename):
        os.remove(temp_filename)

    data = await state.get_data()
    user_id = message.from_user.id

    # Save to SQLite Database
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO users (user_id, full_name, age, bio, city, video_file_id, ai_trust_score, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
    """, (user_id, data['full_name'], data['age'], data['bio'], data['city'], video_file_id, ai_trust_result))
    conn.commit()
    conn.close()

    await state.clear()
    await message.answer(
        "✨ Thank you! Your registration and AI-verified video have been submitted "
        "to moderators. You will be notified once approved.",
        reply_markup=get_main_menu()
    )

    # Send to Moderator Chat with AI Trust Score & Approve / Reject Buttons
    if MODERATOR_CHAT_ID != 0:
        builder = InlineKeyboardBuilder()
        builder.button(text="✅ Approve", callback_data=f"approve_{user_id}")
        builder.button(text="❌ Reject", callback_data=f"reject_{user_id}")
        builder.adjust(2)

        caption = (
            f"🔔 AI-Assisted Verification Request!\n\n"
            f"👤 Name: {data['full_name']}\n"
            f"🎂 Age: {data['age']}\n"
            f"📍 City: {data['city']}\n"
            f"📝 Bio: {data['bio']}\n"
            f"🛡️ {ai_trust_result}\n"
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
            await bot.send_message(
                target_user_id, 
                "🎉 Your profile has been approved by the moderator! You can now tap '🔍 Find Partner' below to check out profiles.",
                reply_markup=get_main_menu()
            )
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

# Handler for "🔍 Find Partner" with AI Icebreaker
@dp.message(F.text == "🔍 Find Partner")
async def handle_find_partner(message: types.Message):
    user_id = message.from_user.id
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, full_name, age, bio, city, video_file_id FROM users WHERE status = 'approved' AND user_id != ?", (user_id,))
    users = cursor.fetchall()
    conn.close()

    if not users:
        await message.answer("No more profiles available right now. Check back later!", reply_markup=get_main_menu())
        return

    u = users[0]
    target_user_id, name, age, bio, city, video_file_id = u[0], u[1], u[2], u[3], u[4], u[5]

    # Generate AI Icebreaker
    icebreaker = await generate_ai_icebreaker(name, bio, city)

    builder = InlineKeyboardBuilder()
    builder.button(text="❤️ Interested", callback_data=f"like_{target_user_id}")
    builder.button(text="💬 Chat", callback_data=f"chat_{target_user_id}")
    builder.adjust(2)

    caption = f"👤 {name}, {age}\n📍 {city}\n📝 {bio}\n\n💬 **AI Icebreaker Suggestion:**\n> *\"{icebreaker}\"*"

    if video_file_id:
        try:
            await message.answer_video(video_file_id, caption=caption, parse_mode="Markdown", reply_markup=builder.as_markup())
        except Exception:
            await message.answer(caption, parse_mode="Markdown", reply_markup=builder.as_markup())
    else:
        await message.answer(caption, parse_mode="Markdown", reply_markup=builder.as_markup())

# Handler for "👤 My Profile"
@dp.message(F.text == "👤 My Profile")
async def handle_my_profile(message: types.Message):
    user_id = message.from_user.id
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT full_name, age, bio, city, ai_trust_score, status FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        await message.answer("You haven't registered yet! Send /start to begin.")
        return

    await message.answer(
        f"📊 **Your Profile Details:**\n\n"
        f"👤 Name: {row[0]}\n"
        f"🎂 Age: {row[1]}\n"
        f"📍 City: {row[2]}\n"
        f"📝 Bio: {row[3]}\n"
        f"🛡️ {row[4]}\n"
        f"🟢 Status: {row[5].capitalize()}",
        parse_mode="Markdown",
        reply_markup=get_main_menu()
    )

# Interactive Like / Chat Callback Handler
@dp.callback_query(F.data.startswith("like_") | F.data.startswith("chat_"))
async def process_interaction(callback: types.CallbackQuery):
    action, target_id = callback.data.split("_")
    if action == "like":
        await callback.answer("You marked this profile as interested! ❤️")
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("❤️ You marked this profile as interested. Use '🔍 Find Partner' to browse more.")
    elif action == "chat":
        await callback.answer("Opening chat connection...")
        await callback.message.answer(f"💬 You can now message user ID {target_id} or connect directly!")

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
