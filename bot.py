# ============================================================
# 🤖 bot.py — OCR فارسی/انگلیسی/عربی با دو حالت Fast / Accurate
# ============================================================

import os
import tempfile
import logging
import re
import asyncio
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Thread
from typing import Optional

import pytesseract
from PIL import Image
from pdf2image import convert_from_path
from flask import Flask
from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

# ----------------------------
# 🔧 تنظیمات عمومی
# ----------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
POPPLER_PATH = os.environ.get("POPPLER_PATH", "/usr/bin")

executor = ThreadPoolExecutor(max_workers=4)

# ----------------------------
# 🌐 Flask برای UptimeRobot
# ----------------------------
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "✅ Bot is alive!", 200

def run_flask():
    flask_app.run(host="0.0.0.0", port=10000)

# ----------------------------
# 🧠 تشخیص زبان متن
# ----------------------------
def detect_language(image: Image.Image) -> str:
    try:
        txt = pytesseract.image_to_string(image, lang="fas+eng+ara", config="--psm 6")
        farsi = len(re.findall(r'[\u0600-\u06FF]', txt))
        english = len(re.findall(r'[A-Za-z]', txt))
        arabic = len(re.findall(r'[\u0621-\u064A]', txt))
        if farsi > english and farsi > arabic:
            return "fas"
        elif arabic > farsi:
            return "ara"
        else:
            return "eng"
    except Exception:
        return "fas+eng+ara"

# ----------------------------
# 📄 OCR PDF
# ----------------------------
def ocr_pdf(pdf_path: str, mode: str) -> str:
    dpi = 200 if mode == "fast" else 300
    langs = "fas_fast+eng" if mode == "fast" else "fas+eng+ara"
    images = convert_from_path(pdf_path, dpi=dpi, poppler_path=POPPLER_PATH)
    texts = []
    for img in images:
        text = pytesseract.image_to_string(
            img,
            lang=langs,
            config="--oem 3 --psm 6 -c preserve_interword_spaces=1"
        )
        text = text.replace("ي", "ی").replace("ك", "ک").strip()
        texts.append(text)
    return "\n\n".join(texts).strip()

# ----------------------------
# 🖼️ OCR Image
# ----------------------------
def ocr_image(image_path: str, mode: str) -> str:
    img = Image.open(image_path)
    langs = "fas_fast+eng" if mode == "fast" else "fas+eng+ara"
    text = pytesseract.image_to_string(
        img,
        lang=langs,
        config="--oem 3 --psm 6 -c preserve_interword_spaces=1"
    )
    text = text.replace("ي", "ی").replace("ك", "ک").strip()
    return text

# ----------------------------
# 📨 پردازش فایل دریافتی
# ----------------------------
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    file_id = None
    file_name = None

    if message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name
    elif message.photo:
        file_id = message.photo[-1].file_id
        file_name = f"{message.photo[-1].file_unique_id}.jpg"
    else:
        await message.reply_text("📄 لطفاً فایل PDF یا عکس بفرست.")
        return

    # ذخیره فایل موقت
    tmp_dir = tempfile.mkdtemp()
    local_path = os.path.join(tmp_dir, file_name)
    telegram_file = await context.bot.get_file(file_id)
    await telegram_file.download_to_drive(custom_path=local_path)

    # ساخت دکمه انتخاب حالت OCR
    keyboard = [
        [
            InlineKeyboardButton("⚡ حالت سریع", callback_data=f"mode_fast|{local_path}"),
            InlineKeyboardButton("🎯 حالت دقیق", callback_data=f"mode_accurate|{local_path}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text("کدوم حالت OCR رو می‌خوای؟ 👇", reply_markup=reply_markup)

# ----------------------------
# ⚙️ پاسخ به انتخاب کاربر
# ----------------------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data.split("|")
    mode = "fast" if "mode_fast" in data[0] else "accurate"
    file_path = data[1]

    await query.edit_message_text(f"⏳ در حال پردازش ({'سریع' if mode=='fast' else 'دقیق'})... لطفاً صبر کنید.")

    def process():
        if file_path.lower().endswith(".pdf"):
            return ocr_pdf(file_path, mode)
        else:
            return ocr_image(file_path, mode)

    loop = asyncio.get_running_loop()
    text = await loop.run_in_executor(executor, process)

    if not text.strip():
        await query.message.reply_text("⚠️ متنی پیدا نشد.")
        return

    for i in range(0, len(text), 4000):
        await query.message.reply_text(text[i:i + 4000])

    await query.message.reply_text("✅ استخراج متن انجام شد. متشکرم 🙌")

    # پاک کردن فایل موقت
    try:
        os.remove(file_path)
    except:
        pass

# ----------------------------
# 🚀 فرمان شروع
# ----------------------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 سلام!\n"
        "من ربات OCR هوشمند هستم.\n\n"
        "فقط کافیه فایل PDF یا عکس بفرستی.\n"
        "در مرحله بعد می‌تونی بین دو حالت OCR انتخاب کنی:\n"
        "⚡ سریع (Fast)\n🎯 دقیق (Accurate)"
    )

# ----------------------------
# 🧠 اجرای Flask و Bot
# ----------------------------
def main():
    if not BOT_TOKEN:
        raise RuntimeError("❌ BOT_TOKEN is missing!")

    Thread(target=run_flask).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file))
    app.add_handler(CallbackQueryHandler(button_handler))

    logger.info("🤖 OCR Bot started (Fast/Accurate modes enabled) ...")
    app.run_polling()

if __name__ == "__main__":
    main()
