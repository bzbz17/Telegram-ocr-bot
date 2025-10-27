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
    return "✅ Telegram OCR Bot is alive and running!"


# ===========================
# توابع OCR
# ===========================
def extract_text_from_pdf(pdf_path: str) -> str:
    """استخراج مستقیم متن از PDF اگر قابل انتخاب باشد"""
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
    """OCR برای صفحات PDF تصویری"""
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
    """OCR برای تصویر"""
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
        "من ربات OCR فارسی هستم.\n"
        "📄 لطفاً فایل PDF یا عکس بفرست تا متنش رو برات استخراج کنم ✅"
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
# اجرای همزمان Flask و Bot
# ===========================
async def run_bot():
    app_tg = ApplicationBuilder().token(BOT_TOKEN).build()
    app_tg.add_handler(CommandHandler("start", start))
    app_tg.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file))
    await app_tg.run_polling(stop_signals=None, allowed_updates=Update.ALL_TYPES)


async def run_flask():
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: app.run(host="0.0.0.0", port=8080))


async def main():
    await asyncio.gather(run_flask(), run_bot())


if __name__ == "__main__":
    asyncio.run(main())
