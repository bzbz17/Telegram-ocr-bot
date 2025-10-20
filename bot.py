import os
import tempfile
import logging
import asyncio
from pathlib import Path
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
import pytesseract
from PIL import Image
from pdf2image import convert_from_path
import fitz  # PyMuPDF

# ===========================
# تنظیمات اولیه
# ===========================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
POPPLER_PATH = os.environ.get("POPPLER_PATH", "/usr/bin")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Telegram OCR Bot is running!"


# ===========================
# توابع OCR
# ===========================
def extract_text_from_pdf(pdf_path: str) -> str:
    text = ""
    try:
        with fitz.open(pdf_path) as doc:
            for page in doc:
                txt = page.get_text("text")
                if txt.strip():
                    text += txt + "\n"
    except Exception as e:
        logger.error(f"PDF text extraction error: {e}")
    return text.strip()


def ocr_pdf(pdf_path: str) -> str:
    text_result = []
    try:
        images = convert_from_path(pdf_path, dpi=300, poppler_path=POPPLER_PATH)
        for img in images:
            t = pytesseract.image_to_string(img, lang="fas+eng+ara", config="--psm 6")
            text_result.append(t)
    except Exception as e:
        logger.error(f"OCR PDF error: {e}")
    return "\n".join(text_result).strip()


def ocr_image(image_path: str) -> str:
    try:
        img = Image.open(image_path)
        return pytesseract.image_to_string(img, lang="fas+eng+ara", config="--psm 6").strip()
    except Exception as e:
        logger.error(f"OCR image error: {e}")
        return ""


# ===========================
# Telegram Bot handlers
# ===========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 سلام!\n"
        "من ربات استخراج متن هستم.\n"
        "📄 فقط فایل PDF یا عکس بفرست تا متنش رو برات استخراج کنم ✅"
    )


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
        await message.reply_text("📂 لطفاً فایل PDF یا تصویر بفرست.")
        return

    tmp_dir = tempfile.mkdtemp()
    local_path = os.path.join(tmp_dir, file_name)

    try:
        telegram_file = await context.bot.get_file(file_id)
        await telegram_file.download_to_drive(custom_path=local_path)
        await message.reply_text("⏳ در حال پردازش فایل...")

        # تشخیص نوع فایل
        if file_name.lower().endswith(".pdf"):
            text = extract_text_from_pdf(local_path)
            if not text.strip():
                text = ocr_pdf(local_path)
        else:
            text = ocr_image(local_path)

        if not text.strip():
            await message.reply_text("⚠️ هیچ متنی شناسایی نشد.")
            return

        await message.reply_text(f"📝 متن استخراج‌شده:\n\n{text[:4000]}")

    except Exception as e:
        logger.exception(f"Error processing file: {e}")
        await message.reply_text(f"❌ خطا در پردازش فایل: {str(e)}")
    finally:
        for f in Path(tmp_dir).glob("*"):
            f.unlink(missing_ok=True)
        Path(tmp_dir).rmdir()


# ===========================
# اجرای همزمان Flask + Bot
# ===========================
async def start_bot():
    app_tg = ApplicationBuilder().token(BOT_TOKEN).build()
    app_tg.add_handler(CommandHandler("start", start))
    app_tg.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file))
    await app_tg.run_polling(stop_signals=None, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    # اجرای هم‌زمان Flask و Bot در یک event loop
    loop = asyncio.get_event_loop()
    loop.create_task(start_bot())
    app.run(host="0.0.0.0", port=8080)
