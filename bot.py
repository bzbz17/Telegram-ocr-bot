# ============================================================
# 🤖 bot.py — OCR فارسی/انگلیسی/عربی سریع و دقیق (نسخه بهینه)
# ============================================================

import os
import tempfile
import logging
import re
import asyncio
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
from threading import Thread

import pytesseract
from PIL import Image
from pdf2image import convert_from_path
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# ----------------------------
# تنظیمات اصلی
# ----------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
POPPLER_PATH = os.environ.get("POPPLER_PATH", "/usr/bin")

# هم‌زمانی برای بهبود سرعت OCR
executor = ThreadPoolExecutor(max_workers=4)

# ----------------------------
# Flask برای Ping UptimeRobot
# ----------------------------
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "✅ Bot is alive!", 200

def run_flask():
    flask_app.run(host="0.0.0.0", port=10000)


# ----------------------------
# تشخیص زبان تصویر (فارسی، انگلیسی یا عربی)
# ----------------------------
def detect_language_from_image(image: Image.Image) -> str:
    """زبان غالب متن را با شمارش حروف فارسی و انگلیسی تشخیص می‌دهد."""
    try:
        preview_text = pytesseract.image_to_string(image, lang="fas+eng+ara", config="--psm 6")
        persian_chars = len(re.findall(r'[\u0600-\u06FF]', preview_text))
        english_chars = len(re.findall(r'[A-Za-z]', preview_text))
        arabic_chars = len(re.findall(r'[\u0621-\u064A]', preview_text))

        # اولویت با زبانی است که بیشترین کاراکتر را دارد
        if persian_chars > english_chars and persian_chars > arabic_chars:
            return "fas"
        elif arabic_chars > persian_chars:
            return "ara"
        else:
            return "eng"
    except Exception as e:
        logger.error(f"Language detection error: {e}")
        return "fas+eng+ara"


# ----------------------------
# استخراج متن از PDF (OCR هوشمند)
# ----------------------------
def extract_text_from_pdf(pdf_path: str) -> str:
    """تبدیل صفحات PDF به تصویر و استخراج متن با Tesseract OCR"""
    try:
        images = convert_from_path(pdf_path, dpi=250, poppler_path=POPPLER_PATH)
    except Exception as e:
        logger.error(f"PDF conversion error: {e}")
        return "❌ خطا در باز کردن PDF."

    results = []
    for img in images:
        lang = detect_language_from_image(img)
        text = pytesseract.image_to_string(
            img,
            lang=lang,
            config="--oem 3 --psm 6 -c preserve_interword_spaces=1"
        )
        text = text.replace("ي", "ی").replace("ك", "ک").strip()
        results.append(text)

    return "\n\n".join(results).strip()


# ----------------------------
# استخراج متن از تصویر
# ----------------------------
def extract_text_from_image(image_path: str) -> str:
    """OCR روی تصویر (عکس JPG/PNG)"""
    try:
        img = Image.open(image_path)
        lang = detect_language_from_image(img)
        text = pytesseract.image_to_string(
            img,
            lang=lang,
            config="--oem 3 --psm 6 -c preserve_interword_spaces=1"
        )
        text = text.replace("ي", "ی").replace("ك", "ک").strip()
        return text
    except Exception as e:
        logger.error(f"OCR image error: {e}")
        return "❌ خطا در پردازش تصویر."


# ----------------------------
# هندل فایل‌ها از تلگرام
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
        photo = message.photo[-1]
        file_id = photo.file_id
        file_name = f"{photo.file_unique_id}.jpg"
    else:
        await message.reply_text("📄 لطفاً یک فایل PDF یا عکس بفرستید.")
        return

    tmp_dir = tempfile.mkdtemp()
    local_path = os.path.join(tmp_dir, file_name)

    try:
        telegram_file = await context.bot.get_file(file_id)
        await telegram_file.download_to_drive(custom_path=local_path)
        await message.reply_text("🔍 در حال استخراج متن... لطفاً صبر کنید...")

        def process():
            if file_name.lower().endswith(".pdf"):
                return extract_text_from_pdf(local_path)
            else:
                return extract_text_from_image(local_path)

        loop = asyncio.get_running_loop()
        text = await loop.run_in_executor(executor, process)

        if not text.strip():
            await message.reply_text("⚠️ هیچ متنی پیدا نشد.")
            return

        # اگر متن طولانی بود، در چند پیام بفرست
        for i in range(0, len(text), 4000):
            await message.reply_text(text[i:i + 4000])

        await message.reply_text("✅ استخراج متن با موفقیت انجام شد.")
    except Exception as e:
        logger.exception(f"Error processing file: {e}")
        await message.reply_text(f"❌ خطا: {str(e)}")
    finally:
        try:
            for f in Path(tmp_dir).glob("*"):
                f.unlink(missing_ok=True)
            Path(tmp_dir).rmdir()
        except Exception:
            pass


# ----------------------------
# فرمان شروع
# ----------------------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 سلام!\n"
        "من ربات استخراج متن دقیق هستم.\n\n"
        "📄 فقط کافیه یک فایل PDF یا عکس بفرستی تا متنش رو با دقت بالا استخراج کنم 🔍"
    )


# ----------------------------
# اجرای ربات و Flask همزمان
# ----------------------------
def main():
    if not BOT_TOKEN:
        raise RuntimeError("❌ BOT_TOKEN is missing!")

    # اجرای Flask برای UptimeRobot
    Thread(target=run_flask).start()

    # اجرای ربات
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file))

    logger.info("🤖 OCR Bot started with high accuracy mode + Flask keep-alive")
    app.run_polling()


if __name__ == "__main__":
    main()
