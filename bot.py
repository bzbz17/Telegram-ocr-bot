import os
import logging
import tempfile
from pathlib import Path
import re

import pytesseract
from PIL import Image
from pdf2image import convert_from_path
import fitz  # PyMuPDF
import cv2
import numpy as np
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# ---------------- Logging ----------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------- Environment ----------------
BOT_TOKEN = os.environ.get("BOT_TOKEN")
POPPLER_PATH = os.environ.get("POPPLER_PATH", "/usr/bin")

# ---------------- OCR Language Detection ----------------
def detect_language_from_image(image: Image.Image) -> str:
    """تشخیص خودکار زبان تصویر"""
    try:
        preview_text = pytesseract.image_to_string(image, lang="fas+ara+eng", config="--psm 6")
        persian_chars = len(re.findall(r'[\u0600-\u06FF]', preview_text))
        arabic_chars = len(re.findall(r'[\u0621-\u064A]', preview_text))
        english_chars = len(re.findall(r'[A-Za-z]', preview_text))
        if persian_chars + arabic_chars > english_chars * 1.5:
            return "fas+ara"
        elif english_chars > (persian_chars + arabic_chars):
            return "eng"
        else:
            return "fas+ara+eng"
    except Exception as e:
        logger.error(f"Language detection error: {e}")
        return "fas+ara+eng"

# ---------------- OCR Preprocessing ----------------
def preprocess_image(image_path: str):
    """افزایش دقت OCR با بهبود کیفیت تصویر"""
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return image_path
    img = cv2.bilateralFilter(img, 9, 75, 75)
    _, img = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    temp_path = image_path.replace(".jpg", "_clean.jpg")
    cv2.imwrite(temp_path, img)
    return temp_path

# ---------------- PDF Extraction ----------------
def extract_text_from_pdf(pdf_path: str):
    """استخراج متن از PDF دیجیتال یا اسکن‌شده"""
    text = ""
    try:
        with fitz.open(pdf_path) as doc:
            for page in doc:
                page_text = page.get_text("text")
                if page_text.strip():
                    text += page_text + "\n"
        if text.strip():
            return text.strip()
    except Exception:
        pass

    # در صورت عدم وجود متن دیجیتال، OCR روی تصاویر صفحات
    images = convert_from_path(pdf_path, dpi=250, poppler_path=POPPLER_PATH)
    result_text = []
    for img in images:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_img:
            img.save(tmp_img.name, "JPEG")
            clean_path = preprocess_image(tmp_img.name)
            lang = detect_language_from_image(Image.open(clean_path))
            t = pytesseract.image_to_string(Image.open(clean_path), lang=lang)
            result_text.append(t.strip())
    return "\n".join(result_text).strip()

# ---------------- Image Extraction ----------------
def extract_text_from_image(image_path: str):
    """OCR تصویر با تشخیص زبان و بهبود کیفیت"""
    clean_path = preprocess_image(image_path)
    lang = detect_language_from_image(Image.open(clean_path))
    text = pytesseract.image_to_string(Image.open(clean_path), lang=lang)
    return text.strip()

# ---------------- Telegram Handlers ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 سلام!\n"
        "من ربات استخراج متن هستم 📖\n\n"
        "📄 فقط کافیه یک فایل PDF یا عکس بفرستی تا متن فارسی، انگلیسی یا عربی داخلش رو برات نمایش بدم ✅"
    )

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    file = None
    file_name = None
    if message.document:
        file = message.document
        file_name = file.file_name
    elif message.photo:
        file = message.photo[-1]
        file_name = f"{file.file_unique_id}.jpg"
    else:
        await message.reply_text("📂 لطفاً یک فایل PDF یا عکس ارسال کنید.")
        return

    tmp_dir = tempfile.mkdtemp()
    local_path = os.path.join(tmp_dir, file_name)
    telegram_file = await context.bot.get_file(file.file_id)
    await telegram_file.download_to_drive(custom_path=local_path)

    await message.reply_text("⏳ در حال پردازش و استخراج متن... لطفاً صبر کنید...")

    try:
        if file_name.lower().endswith(".pdf"):
            text = extract_text_from_pdf(local_path)
        else:
            text = extract_text_from_image(local_path)

        if not text.strip():
            await message.reply_text("⚠️ متنی در فایل پیدا نشد.")
        else:
            await message.reply_text(f"📝 متن استخراج‌شده:\n\n{text}")

    except Exception as e:
        logger.exception(f"Error while processing file: {e}")
        await message.reply_text(f"❌ خطا در پردازش فایل: {str(e)}")
    finally:
        for f in Path(tmp_dir).glob("*"):
            f.unlink(missing_ok=True)
        Path(tmp_dir).rmdir()

# ---------------- Run Bot ----------------
def main():
    if not BOT_TOKEN:
        raise RuntimeError("❌ BOT_TOKEN تعریف نشده است!")

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file))

    logger.info("🤖 Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
