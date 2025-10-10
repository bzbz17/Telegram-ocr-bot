import os
import tempfile
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

import pytesseract
from PIL import Image
from pdf2image import convert_from_path
import fitz  # PyMuPDF
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# ---- تنظیمات لاگ ----
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get('BOT_TOKEN')
POPPLER_PATH = os.environ.get('POPPLER_PATH', '/usr/bin')

# ---- پردازش موازی ----
executor = ThreadPoolExecutor(max_workers=int(os.environ.get('OCR_THREADS', 4)))


def detect_language_from_image(image: Image.Image) -> str:
    """تشخیص زبان غالب در تصویر"""
    try:
        preview_text = pytesseract.image_to_string(image, lang="fas+eng", config="--psm 6")
        persian_chars = len(re.findall(r'[\u0600-\u06FF]', preview_text))
        english_chars = len(re.findall(r'[A-Za-z]', preview_text))
        if persian_chars > english_chars * 1.5:
            return "fas"
        elif english_chars > persian_chars * 1.5:
            return "eng"
        else:
            return "fas+eng"
    except Exception:
        return "fas+eng"


def extract_text_from_pdf_digital(pdf_path: str) -> str:
    """استخراج متن دیجیتال از PDF"""
    try:
        text = []
        with fitz.open(pdf_path) as doc:
            for page in doc:
                page_text = page.get_text("text")
                if page_text:
                    text.append(page_text)
        return "\n".join(text).strip()
    except Exception as e:
        logger.error(f"PDF extraction error: {e}")
        return ""


def ocr_pdf_to_text(pdf_path: str, poppler_path: Optional[str] = None) -> str:
    """OCR از PDF اسکن‌شده"""
    try:
        images = convert_from_path(pdf_path, dpi=250, poppler_path=poppler_path)
    except Exception as e:
        logger.error(f"PDF conversion error: {e}")
        return ""

    results = []
    for img in images:
        lang = detect_language_from_image(img)
        text = pytesseract.image_to_string(img, lang=lang, config="--psm 6 --oem 3")
        results.append(text)
    return "\n\n".join(results).strip()


def ocr_image_to_text(image_path: str) -> str:
    """OCR از عکس"""
    try:
        img = Image.open(image_path)
        lang = detect_language_from_image(img)
        return pytesseract.image_to_string(img, lang=lang, config="--psm 6 --oem 3").strip()
    except Exception as e:
        logger.error(f"OCR image error: {e}")
        return ""


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
        await message.reply_text("📄 لطفاً یک فایل PDF یا تصویر ارسال کنید.")
        return

    tmp_dir = tempfile.mkdtemp()
    local_path = os.path.join(tmp_dir, file_name)

    try:
        telegram_file = await context.bot.get_file(file_id)
        await telegram_file.download_to_drive(custom_path=local_path)

        await message.reply_text("⏳ در حال پردازش و استخراج متن ...")

        def process():
            if file_name.lower().endswith(".pdf"):
                text = extract_text_from_pdf_digital(local_path)
                if not text.strip():
                    text = ocr_pdf_to_text(local_path, poppler_path=POPPLER_PATH)
            else:
                text = ocr_image_to_text(local_path)
            return text

        text = await context.application.run_in_executor(executor, process)

        if not text.strip():
            await message.reply_text("⚠️ متنی قابل استخراج نبود.")
            return

        # اگر متن خیلی طولانی بود، در چند پیام ارسال میشه
        max_len = 4000
        chunks = [text[i:i+max_len] for i in range(0, len(text), max_len)]
        for idx, part in enumerate(chunks):
            await message.reply_text(part)

    except Exception as e:
        logger.exception(e)
        await message.reply_text(f"❌ خطا در پردازش فایل: {e}")
    finally:
        for f in Path(tmp_dir).glob("*"):
            f.unlink(missing_ok=True)
        Path(tmp_dir).rmdir()


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 سلام!\n"
        "من ربات استخراج متن هوشمند هستم 🤖\n\n"
        "📸 عکس یا فایل PDF بفرست تا متن فارسی یا انگلیسی‌شو برات استخراج کنم."
    )


def main():
    if not BOT_TOKEN:
        raise RuntimeError("❌ BOT_TOKEN تعریف نشده!")

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file))

    logger.info("🤖 Bot is running ...")
    app.run_polling()


if __name__ == "__main__":
    main()
