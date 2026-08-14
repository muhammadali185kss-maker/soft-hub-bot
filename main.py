import asyncio
import sqlite3
import os
import random
import urllib.parse
from google import genai
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    InlineQuery, 
    InlineQueryResultArticle, 
    InputTextMessageContent,
    InlineKeyboardMarkup, 
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    WebAppInfo,
    BufferedInputFile
)
import aiohttp
from gtts import gTTS

# --- CONFIG & SOZLAMALAR ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
CHANNEL_ID = -1004362617178  

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

ai_client = genai.Client(api_key=GEMINI_API_KEY)
DB_NAME = "soft_hub.db"

class BotState(StatesGroup):
    gemini_mode = State()
    image_gen_mode = State()
    gemini_image_mode = State()  # <-- Rasm tahlil qilish rejimi uchun qo'shildi
    waiting_for_id = State()
    waiting_for_password = State()

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id TEXT NOT NULL,
            file_name TEXT NOT NULL,
            caption TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users_access (
            user_id INTEGER PRIMARY KEY,
            password TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def save_file_to_db(file_id: str, file_name: str, caption: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM files WHERE file_id = ?", (file_id,))
    if not cursor.fetchone():
        cursor.execute("""
            INSERT INTO files (file_id, file_name, caption)
            VALUES (?, ?, ?)
        """, (file_id, file_name, caption.lower()))
        conn.commit()
    conn.close()

def search_files(query: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    if not query:
        cursor.execute("SELECT id, file_name FROM files LIMIT 20")
    else:
        cursor.execute("SELECT id, file_name FROM files WHERE file_name LIKE ? OR caption LIKE ?", 
                       (f"%{query.lower()}%", f"%{query.lower()}%"))
    results = cursor.fetchall()
    conn.close()
    return results

def get_file(db_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT file_id, file_name FROM files WHERE id = ?", (db_id,))
    res = cursor.fetchone()
    conn.close()
    return res

init_db()

# --- MENYULAR ---
main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="💻 Dasturlar (Soft)"), KeyboardButton(text="🤖 Google Gemini AI")],
        [KeyboardButton(text="🎨 Rasm chizish (AI)"), KeyboardButton(text="🌐 Google Web Search")],
        [KeyboardButton(text="ℹ️ Yordam")]
    ],
    resize_keyboard=True
)

gemini_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🖼️ Rasm tahlil qilish (AI)")], # <-- Menyuga rasm tahlil tugmasi qo'shildi
        [KeyboardButton(text="⬅️ Chiqish")]
    ],
    resize_keyboard=True
)

google_web_btn = InlineKeyboardMarkup(
    inline_keyboard=[[
        InlineKeyboardButton(text="🚀 Google Web App-ni ochish", web_app=WebAppInfo(url="https://www.google.com"))
    ]]
)

# --- START & RESET ---
@dp.message(CommandStart())
async def start_cmd(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    user_name = message.from_user.first_name or "do'st"

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT password FROM users_access WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()

    if not row:
        user_password = str(random.randint(1000, 9999))
        cursor.execute("INSERT INTO users_access (user_id, password) VALUES (?, ?)", (user_id, user_password))
        conn.commit()
    else:
        user_password = row[0]
    conn.close()

    text = (
        f"👋 **Xush kelibsiz, {user_name}!**\n\n"
        f"🔑 **Sizning shaxsiy kirish ma'lumotlaringiz:**\n"
        f"🆔 **Sizning ID:** `{user_id}`\n"
        f"🔒 **Sizning Parolingiz:** `{user_password}`\n\n"
        "💡 *Parolingiz esdan chiqsa, /reset buyrug'ini yuboring.*"
    )
    await message.answer(text, reply_markup=main_menu, parse_mode="Markdown")

@dp.message(Command("reset"))
async def reset_password(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    new_password = str(random.randint(1000, 9999))
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO users_access (user_id, password) VALUES (?, ?)", (user_id, new_password))
    conn.commit()
    conn.close()

    await message.answer(
        f"🔄 **Parolingiz yangilandi!**\n\n🆔 **ID:** `{user_id}`\n🔒 **Yangi Parol:** `{new_password}`",
        reply_markup=main_menu,
        parse_mode="Markdown"
    )

@dp.message(F.text == "🌐 Google Web Search")
async def google_app_handler(message: types.Message):
    await message.answer("🖥️ **Google Web Search:**", reply_markup=google_web_btn)

@dp.message(F.text == "ℹ️ Yordam")
async def help_handler(message: types.Message):
    await message.answer("ℹ️ **Yordam bo'limi:**\nMurojaat uchun: [Ali](https://t.me/ali_07m)", parse_mode="Markdown")

# --- LOGIN JARAYONI ---
@dp.message(F.text == "💻 Dasturlar (Soft)")
async def open_modal_window(message: types.Message, state: FSMContext):
    await state.set_state(BotState.waiting_for_id)
    await message.answer("🆔 **Iltimos, Telegram ID ingizni kiriting:**", parse_mode="Markdown")

@dp.message(BotState.waiting_for_id)
async def process_user_id(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ **Xato!** Faqat raqamlardan iborat ID kiriting:")
        return
    
    await state.update_data(entered_id=int(message.text))
    await state.set_state(BotState.waiting_for_password)
    await message.answer("🔒 **Endi ushbu ID ga tegishli Parolni kiriting:**", parse_mode="Markdown")

@dp.message(BotState.waiting_for_password)
async def process_user_password(message: types.Message, state: FSMContext):
    data = await state.get_data()
    entered_id = data.get("entered_id")
    entered_password = message.text.strip()

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT password FROM users_access WHERE user_id = ?", (entered_id,))
    row = cursor.fetchone()
    conn.close()

    if row and row[0] == entered_password:
        await state.clear()
        search_markup = InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(text="🔍 Dasturlarni qidirish", switch_inline_query_current_chat="")
            ]]
        )
        await message.answer(
            "✅ **Muvaffaqiyatli kiritildi!**\n"
            "Quyidagi tugmani bosib kerakli dasturni qidirishingiz mumkin:",
            reply_markup=search_markup,
            parse_mode="Markdown"
        )
    else:
        await state.clear()
        await message.answer("❌ **ID yoki Parol noto'g'ri!** Qaytadan urinish uchun tugmani bosing.", reply_markup=main_menu, parse_mode="Markdown")

# --- INLINE QIDIRUV ---
@dp.inline_query()
async def inline_search_handler(inline_query: InlineQuery):
    query = inline_query.query.strip()
    db_results = search_files(query)
    results = []

    for db_id, file_name in db_results:
        results.append(
            InlineQueryResultArticle(
                id=str(db_id),
                title=file_name,
                description="Yuklab olish uchun bosing",
                input_message_content=InputTextMessageContent(
                    message_text=f"🔍 **Topilgan fayl:** {file_name}\n\nYuklab olish uchun pastdagi tugmani bosing:"
                ),
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[
                        InlineKeyboardButton(text="📥 Faylni yuklab olish", callback_data=f"down:{db_id}")
                    ]]
                )
            )
        )
    await inline_query.answer(results, cache_time=0)

@dp.channel_post(F.chat.id == CHANNEL_ID)
@dp.edited_channel_post(F.chat.id == CHANNEL_ID)
async def auto_save_channel_file(message: types.Message):
    if message.document:
        doc = message.document
        save_file_to_db(doc.file_id, doc.file_name or "Fayl", message.caption or doc.file_name)

@dp.message(F.document)
async def auto_save_direct_file(message: types.Message):
    doc = message.document
    save_file_to_db(doc.file_id, doc.file_name or "Fayl", message.caption or doc.file_name)
    await message.reply(f"✅ **'{doc.file_name}'** bazaga saqlandi!")

@dp.callback_query(F.data.startswith("down:"))
async def send_requested_file(callback: types.CallbackQuery):
    db_id = int(callback.data.split(":")[1])
    file_info = get_file(db_id)
    if file_info:
        file_id, file_name = file_info
        await bot.send_document(chat_id=callback.from_user.id, document=file_id, caption=f"📥 **{file_name}**")
        await callback.answer("✅ Fayl yuborildi!")
    else:
        await callback.answer("⚠️ Topilmadi!", show_alert=True)

# --- RASM CHIZISH (AI IMAGE GENERATION) ---
@dp.message(F.text == "🎨 Rasm chizish (AI)")
async def start_image_gen(message: types.Message, state: FSMContext):
    await state.set_state(BotState.image_gen_mode)
    await message.answer(
        "🎨 **Rasm chizish rejimi yoqildi!**\n"
        "Qanday rasm chizish kerakligini yozib yuboring (masalan: *'BMW M4 sport car in neon city'* yoki *'Qizil gullar'*, imkon qadar ingliz tilida yozsangiz, rasm chiroyli chiqadi):",
        reply_markup=gemini_menu
    )

@dp.message(BotState.image_gen_mode, F.text == "⬅️ Chiqish")
async def exit_image_gen(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Bosh menyuga qaytdingiz.", reply_markup=main_menu)

@dp.message(BotState.image_gen_mode, F.text)
async def generate_image_handler(message: types.Message):
    wait_msg = await message.answer("🖼️ Sun'iy intellekt rasm chizmoqda, biroz kuting...")
    
    user_prompt = message.text.strip()
    encoded_prompt = urllib.parse.quote(user_prompt)
    seed = random.randint(1, 999999)
    
    image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&seed={seed}&nologo=true"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(image_url) as resp:
                if resp.status == 200:
                    image_bytes = await resp.read()
                    photo_file = BufferedInputFile(image_bytes, filename="ai_image.jpg")
                    
                    await message.answer_photo(
                        photo=photo_file, 
                        caption=f"✨ **Sizning so'rovingiz bo'yicha chizildi:**\n_{user_prompt}_", 
                        parse_mode="Markdown"
                    )
                    await wait_msg.delete()
                    return

        await wait_msg.edit_text("❌ Rasm yaratishda xatolik yuz berdi. Boshqa so'z bilan urinib ko'ring.")
    except Exception as e:
        await wait_msg.edit_text(f"❌ Xatolik: {str(e)}")

# --- GEMINI AI (MATN, OVOZ VA RASM TAHLILI) ---
@dp.message(F.text == "🤖 Google Gemini AI")
async def start_gemini(message: types.Message, state: FSMContext):
    await state.set_state(BotState.gemini_mode)
    await message.answer(
        "🧠 **Google Gemini AI (3.6 Flash) yoqildi!**\n"
        "• Savolingizni matn yoki ovozli xabar ko'rinishida yuboring.\n"
        "• Yoki '🖼️ Rasm tahlil qilish (AI)' tugmasini bosib rasm yuborishingiz mumkin.", 
        reply_markup=gemini_menu
    )

@dp.message(BotState.gemini_mode, F.text == "⬅️ Chiqish")
async def exit_gemini(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Bosh menyuga qaytdingiz.", reply_markup=main_menu)

# Rasm tahlil qilish rejimiga o'tish
@dp.message(BotState.gemini_mode, F.text == "🖼️ Rasm tahlil qilish (AI)")
async def start_gemini_image_mode(message: types.Message, state: FSMContext):
    await state.set_state(BotState.gemini_image_mode)
    await message.answer(
        "📸 **Rasm tahlil qilish rejimi yoqildi!**\n"
        "Menga istalgan rasmni yuboring va xohlasangiz unga izoh (savol) yozib qoldiring.",
        reply_markup=gemini_menu
    )

@dp.message(BotState.gemini_image_mode, F.text == "⬅️ Chiqish")
async def exit_gemini_image_mode(message: types.Message, state: FSMContext):
    await state.set_state(BotState.gemini_mode)
    await message.answer("Gemini matn rejimiga qaytdingiz.", reply_markup=gemini_menu)

# Rasmni qabul qilib tahlil qilish
@dp.message(BotState.gemini_image_mode, F.photo)
async def gemini_analyze_photo(message: types.Message):
    wait_msg = await message.answer("🔍 Rasm tahlil qilinmoqda, biroz kuting...")
    photo_path = "temp_analysis_photo.jpg"
    response_audio_path = "response.mp3"
    
    try:
        photo = message.photo[-1]
        file_info = await bot.get_file(photo.file_id)
        await bot.download_file(file_info.file_path, photo_path)

        image_ref = ai_client.files.upload(file=photo_path)
        user_caption = message.caption or "Iltimos, bu rasmni batafsil tahlil qilib tushuntirib bering."

        response = ai_client.models.generate_content(
            model="gemini-3.6-flash",
            contents=[image_ref, user_caption]
        )
        ai_text = response.text
        
        await wait_msg.edit_text(ai_text)

        # Javobni ovozga aylantirish
        tts = gTTS(text=ai_text, lang='ru')
        tts.save(response_audio_path)

        with open(response_audio_path, "rb") as audio_file:
            voice_bytes = audio_file.read()
            voice_file = BufferedInputFile(voice_bytes, filename="voice_response.mp3")
            await message.answer_voice(voice=voice_file, caption="🎙️ Tahlil bo'yicha ovozli javob")

    except Exception as e:
        await wait_msg.edit_text(f"❌ Xatolik yuz berdi: {str(e)}")
    finally:
        if os.path.exists(photo_path):
            os.remove(photo_path)
        if os.path.exists(response_audio_path):
            os.remove(response_audio_path)

@dp.message(BotState.gemini_mode, F.voice)
async def gemini_voice_handler(message: types.Message):
    wait_msg = await message.answer("🎙️ Ovozli xabar tinglanmoqda va tahlil qilinmoqda...")
    audio_file_path = "temp_voice.ogg"
    response_audio_path = "response.mp3"
    try:
        voice = message.voice
        file_info = await bot.get_file(voice.file_id)
        await bot.download_file(file_info.file_path, audio_file_path)

        audio_file_ref = ai_client.files.upload(file=audio_file_path)

        response = ai_client.models.generate_content(
            model="gemini-3.6-flash",
            contents=[audio_file_ref, "Iltimos, ushbu ovozli xabardagi savolga to'g'ridan-to'g'ri va tushunarli qilib javob ber."]
        )
        ai_text = response.text
        
        await wait_msg.edit_text(ai_text)

        tts = gTTS(text=ai_text, lang='ru')
        tts.save(response_audio_path)

        with open(response_audio_path, "rb") as audio_file:
            voice_bytes = audio_file.read()
            voice_file = BufferedInputFile(voice_bytes, filename="voice_response.mp3")
            await message.answer_voice(voice=voice_file, caption="🎙️ Ovozli javob")

    except Exception as e:
        await wait_msg.edit_text(f"❌ Xatolik yuz berdi: {str(e)}")
    finally:
        if os.path.exists(audio_file_path):
            os.remove(audio_file_path)
        if os.path.exists(response_audio_path):
            os.remove(response_audio_path)

@dp.message(BotState.gemini_mode, F.text)
async def gemini_chat(message: types.Message):
    wait_msg = await message.answer("🤔 O'ylanmoqda...")
    max_retries = 3
    retry_delay = 10
    response_audio_path = "response.mp3"

    for attempt in range(max_retries):
        try:
            response = ai_client.models.generate_content(
                model="gemini-3.6-flash", 
                contents=message.text
            )
            ai_text = response.text
            
            await wait_msg.edit_text(ai_text)

            tts = gTTS(text=ai_text, lang='ru')
            tts.save(response_audio_path)

            with open(response_audio_path, "rb") as audio_file:
                voice_bytes = audio_file.read()
                voice_file = BufferedInputFile(voice_bytes, filename="voice_response.mp3")
                await message.answer_voice(voice=voice_file, caption="🎙️ Ovozli javob")

            if os.path.exists(response_audio_path):
                os.remove(response_audio_path)
            return

        except Exception as e:
            error_str = str(e)
            if ("429" in error_str or "RESOURCE_EXHAUSTED" in error_str or "503" in error_str) and attempt < max_retries - 1:
                await wait_msg.edit_text(f"⏳ Server band. {retry_delay} soniyadan so'ng qayta urinilmoqda... ({attempt + 1}/{max_retries})")
                await asyncio.sleep(retry_delay)
            else:
                await wait_msg.edit_text(f"❌ Xatolik yuz berdi: {error_str}")
                break
        finally:
            if os.path.exists(response_audio_path):
                os.remove(response_audio_path)

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    print("🚀 Bot ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())