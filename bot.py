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

from telegram import Update, InputFile
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get('BOT_TOKEN')
POPPLER_PATH = os.environ.get('POPPLER_PATH', '/usr/bin')


def detect_language_from_image(image: Image.Image) -> str:
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
    except Exception as e:
        logger.error(f"Language detection error: {e}")
        return "fas+eng"


def extract_text_from_pdf_digital(pdf_path: str) -> str:
    text_result = []
    try:
        with fitz.open(pdf_path) as doc:
            for page in doc:
                txt = page.get_text("text")
                if txt and isinstance(txt, str):
                    text_result.append(txt.strip())
    except Exception as e:
        logger.error(f"PDF text extraction error: {e}")
    return "\n".join(text_result).strip()


def ocr_pdf_to_text(pdf_path: str, poppler_path: Optional[str] = None) -> str:
    try:
        images = convert_from_path(pdf_path, dpi=300, poppler_path=poppler_path)
    except Exception as e:
        logger.error(f"PDF to image error: {e}")
        return ""

    texts = []
    for img in images:
        lang = detect_language_from_image(img)
        t = pytesseract.image_to_string(img, lang=lang)
        if t and isinstance(t, str):
            texts.append(t.strip())
    return "\n\n".join(texts).strip()


def ocr_image_to_text(image_path: str) -> str:
    try:
        img = Image.open(image_path)
        lang = detect_language_from_image(img)
        text = pytesseract.image_to_string(img, lang=lang)
        if text and isinstance(text, str):
            return text.strip()
        return ""
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
        await message.reply_text("📄 لطفاً یک فایل PDF یا عکس بفرستید.")
        return

    tmp_dir = tempfile.mkdtemp()
    local_path = os.path.join(tmp_dir, file_name)

    try:
        telegram_file = await context.bot.get_file(file_id)
        await telegram_file.download_to_drive(custom_path=local_path)

        if file_name.lower().endswith(".pdf"):
            await message.reply_text("📑 در حال استخراج متن از PDF ...")
            text = extract_text_from_pdf_digital(local_path)
            if not text:
                await message.reply_text("🔍 متن دیجیتال یافت نشد، اجرای OCR با تشخیص زبان ...")
                text = ocr_pdf_to_text(local_path, poppler_path=POPPLER_PATH)
        else:
            await message.reply_text("🖼️ در حال اجرای OCR روی تصویر (با تشخیص زبان)...")
            text = ocr_image_to_text(local_path)

        logger.info(f"🔍 مقدار نهایی text:\n{text[:100]}")

        if not text or not isinstance(text, str):
            await message.reply_text("⚠️ هیچ متنی قابل استخراج نبود.")
            return

        txt_name = Path(file_name).stem + ".txt"
        txt_path = os.path.join(tmp_dir, txt_name)
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(text)

        preview = text[:500]
        if len(text) > 500:
            preview += "\n\n📄 ادامه متن در فایل ضمیمه است..."

        await message.reply_text(f"📝 پیش‌نمایش متن:\n\n{preview}")

        await message.reply_document(
            document=InputFile(txt_path, filename=txt_name),
            caption="📎 فایل متنی استخراج‌شده آماده است ✅"
        )

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
        "📄 فایل PDF یا عکس بفرست تا متن فارسی یا انگلیسی‌شو برات تشخیص بدم و استخراج کنم."
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
