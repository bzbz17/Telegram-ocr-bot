import os
import tempfile
import logging
from pathlib import Path
from typing import Optional
import re
import pytesseract
from PIL import Image
from pdf2image import convert_from_path
import fitz  # PyMuPDF
from concurrent.futures import ThreadPoolExecutor

from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get('BOT_TOKEN')
POPPLER_PATH = os.environ.get('POPPLER_PATH', '/usr/bin')

# بهبود سرعت OCR با ThreadPool
executor = ThreadPoolExecutor(max_workers=4)

# 🎯 تنظیمات ویژه برای دقت فارسی
OCR_CONFIG = "--oem 3 --psm 6 -c preserve_interword_spaces=1"


def detect_language_from_image(image: Image.Image) -> str:
    """تشخیص زبان غالب (فارسی یا انگلیسی)"""
    try:
        preview_text = pytesseract.image_to_string(image, lang="fas+eng", config=OCR_CONFIG)
        persian_chars = len(re.findall(r'[\u0600-\u06FF]', preview_text))
        english_chars = len(re.findall(r'[A-Za-z]', preview_text))
        if persian_chars > english_chars * 1.5:
            return "fas"
        elif english_chars > persian_chars * 1.5:
            return "eng"
        else:
            return "fas+eng"
    except Exception as e:
        logger.error(f"Language detection error: {e}")
        return "fas+eng"


def extract_text_from_pdf_digital(pdf_path: str) -> str:
    """استخراج مستقیم متن دیجیتال PDF"""
    text_result = []
    try:
        with fitz.open(pdf_path) as doc:
            for page in doc:
                txt = page.get_text("text")
                if txt:
                    text_result.append(txt)
    except Exception as e:
        logger.error(f"PDF text extraction error: {e}")
    return "\n".join(text_result).strip()


def ocr_image_to_text(image: Image.Image, lang: str = "fas+eng") -> str:
    """OCR روی تصویر با دقت بالا"""
    try:
        return pytesseract.image_to_string(image, lang=lang, config=OCR_CONFIG).strip()
    except Exception as e:
        logger.error(f"OCR error: {e}")
        return ""


def ocr_pdf_to_text(pdf_path: str, poppler_path: Optional[str] = None) -> str:
    """OCR روی PDF اسکن‌شده با تشخیص زبان"""
    try:
        images = convert_from_path(pdf_path, dpi=300, poppler_path=poppler_path)
    except Exception as e:
        logger.error(f"PDF to image error: {e}")
        return ""

    texts = []

    def process_page(img):
        lang = detect_language_from_image(img)
        return ocr_image_to_text(img, lang)

    results = list(executor.map(process_page, images))
    for res in results:
        if res:
            texts.append(res)
    return "\n\n".join(texts).strip()


async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    if message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name
    elif message.photo:
        file_id = message.photo[-1].file_id
        file_name = f"{message.photo[-1].file_unique_id}.jpg"
    else:
        await message.reply_text("📄 لطفاً فایل PDF یا تصویر ارسال کنید.")
        return

    tmp_dir = tempfile.mkdtemp()
    local_path = os.path.join(tmp_dir, file_name)

    try:
        telegram_file = await context.bot.get_file(file_id)
        await telegram_file.download_to_drive(custom_path=local_path)

        if file_name.lower().endswith(".pdf"):
            await message.reply_text("📑 در حال استخراج متن از PDF ...")
            text = extract_text_from_pdf_digital(local_path)
            if not text.strip():
                await message.reply_text("🔍 متن دیجیتال یافت نشد. در حال اجرای OCR ...")
                text = ocr_pdf_to_text(local_path, poppler_path=POPPLER_PATH)
        else:
            await message.reply_text("🖼️ در حال استخراج متن از تصویر ...")
            img = Image.open(local_path)
            lang = detect_language_from_image(img)
            text = ocr_image_to_text(img, lang)

        if not text.strip():
            await message.reply_text("⚠️ هیچ متنی قابل استخراج نبود.")
            return

        # ✨ ارسال متن به صورت تکه‌تکه (در صورت طولانی بودن)
        max_len = 3900  # محدودیت تلگرام
        for i in range(0, len(text), max_len):
            part = text[i:i + max_len]
            await message.reply_text(part)

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


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 سلام!\n"
        "من ربات استخراج متن هوشمند هستم.\n\n"
        "📄 فایل PDF یا عکس بفرست تا متن فارسی یا انگلیسی‌شو برات با بالاترین دقت و سرعت استخراج کنم."
    )


def main():
    if not BOT_TOKEN:
        raise RuntimeError("❌ BOT_TOKEN is missing!")

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file))

    logger.info("🤖 Bot started and waiting for files...")
    app.run_polling()


if __name__ == "__main__":
    main()
