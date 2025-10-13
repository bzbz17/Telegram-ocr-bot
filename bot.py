# ============================================================
# 🤖 bot.py — OCR فارسی / عربی / انگلیسی با EasyOCR + ocrmypdf + Flask
# ============================================================

import os
import tempfile
import logging
import asyncio
from pathlib import Path
from threading import Thread
import re
import cv2
import numpy as np
from PIL import Image

import pytesseract
import fitz  # PyMuPDF
import easyocr
import ocrmypdf
import arabic_reshaper
from bidi.algorithm import get_display
from flask import Flask
from pdf2image import convert_from_path
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# ----------------------------
# 🔧 تنظیمات عمومی
# ----------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
POPPLER_PATH = os.environ.get("POPPLER_PATH", "/usr/bin")
LANGS = ["fa", "ar", "en"]

reader = easyocr.Reader(LANGS, gpu=False)

# ----------------------------
# 🌐 Flask برای UptimeRobot
# ----------------------------
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "✅ OCR Bot is alive!", 200

def run_flask():
    flask_app.run(host="0.0.0.0", port=10000)

# ----------------------------
# 🧠 پیش‌پردازش تصویر
# ----------------------------
def preprocess_image(image_path: str) -> np.ndarray:
    """پیش‌پردازش تصویر برای بهبود OCR"""
    img = cv2.imread(image_path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # حذف نویز
    gray = cv2.fastNlMeansDenoising(gray, None, 30, 7, 21)
    # باینری‌سازی (سیاه و سفید)
    _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # تصحیح زاویه (deskew)
    coords = np.column_stack(np.where(th > 0))
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
    (h, w) = th.shape[:2]
    M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
    rotated = cv2.warpAffine(th, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    return rotated

# ----------------------------
# 📄 OCR PDF (با پشتیبانی از PDFهای اسکن‌شده)
# ----------------------------
def extract_text_from_pdf(pdf_path: str) -> str:
    """استخراج متن از PDF — هم دیجیتال هم اسکن‌شده"""
    try:
        text = ""
        # 1. تلاش برای خواندن متن دیجیتال
        with fitz.open(pdf_path) as doc:
            for page in doc:
                t = page.get_text("text")
                if t.strip():
                    text += t + "\n"

        # اگر متن دیجیتال نداشت → OCR
        if not text.strip():
            logger.info("📄 No digital text found — performing OCR via ocrmypdf...")
            temp_out = tempfile.mktemp(suffix=".pdf")
            ocrmypdf.ocr(pdf_path, temp_out, language="fas+ara+eng", progress_bar=False)
            images = convert_from_path(temp_out, dpi=300, poppler_path=POPPLER_PATH)
            results = []
            for img in images:
                tmp = tempfile.mktemp(suffix=".png")
                img.save(tmp, "PNG")
                processed = preprocess_image(tmp)
                text_ocr = pytesseract.image_to_string(
                    processed,
                    lang="fas+ara+eng",
                    config="--oem 3 --psm 6 -c preserve_interword_spaces=1"
                )
                results.append(text_ocr)
            text = "\n".join(results)

        # اصلاح خروجی
        text = text.replace("ي", "ی").replace("ك", "ک")
        text = arabic_reshaper.reshape(text)
        text = get_display(text)
        return text.strip()
    except Exception as e:
        logger.error(f"PDF OCR error: {e}")
        return "❌ خطا در استخراج متن از PDF."

# ----------------------------
# 🖼️ OCR Image
# ----------------------------
def extract_text_from_image(image_path: str) -> str:
    """OCR از عکس با ترکیب EasyOCR و Tesseract"""
    try:
        processed = preprocess_image(image_path)
        # استفاده از EasyOCR
        results = reader.readtext(processed, detail=0, paragraph=True)
        text_easy = "\n".join(results)

        # ترکیب با pytesseract برای دقت بیشتر
        text_tess = pytesseract.image_to_string(
            processed,
            lang="fas+ara+eng",
            config="--oem 3 --psm 6 -c preserve_interword_spaces=1"
        )
        text = text_easy + "\n" + text_tess
        text = text.replace("ي", "ی").replace("ك", "ک")
        text = arabic_reshaper.reshape(text)
        text = get_display(text)
        return text.strip()
    except Exception as e:
        logger.error(f"OCR image error: {e}")
        return "❌ خطا در پردازش تصویر."

# ----------------------------
# 📨 مدیریت فایل ارسالی از تلگرام
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
        await message.reply_text("📄 لطفاً یک فایل PDF یا عکس بفرستید.")
        return

    tmp_dir = tempfile.mkdtemp()
    local_path = os.path.join(tmp_dir, file_name)

    try:
        telegram_file = await context.bot.get_file(file_id)
        await telegram_file.download_to_drive(custom_path=local_path)
        await message.reply_text("🔍 در حال استخراج متن... لطفاً صبر کنید.")

        def process():
            if file_name.lower().endswith(".pdf"):
                return extract_text_from_pdf(local_path)
            else:
                return extract_text_from_image(local_path)

        loop = asyncio.get_running_loop()
        text = await loop.run_in_executor(None, process)

        if not text.strip():
            await message.reply_text("⚠️ هیچ متنی پیدا نشد.")
            return

        # تقسیم متن طولانی
        for i in range(0, len(text), 4000):
            await message.reply_text(text[i:i + 4000])

        await message.reply_text("✅ استخراج متن با موفقیت انجام شد.")
    except Exception as e:
        logger.exception(e)
        await message.reply_text(f"❌ خطا: {str(e)}")
    finally:
        for f in Path(tmp_dir).glob("*"):
            f.unlink(missing_ok=True)
        Path(tmp_dir).rmdir()

# ----------------------------
# 🚀 دستور شروع
# ----------------------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 سلام!\n"
        "من ربات OCR حرفه‌ای هستم.\n\n"
        "📄 فایل PDF یا عکس بفرست تا متن فارسی، عربی یا انگلیسی‌شو با دقت بالا استخراج کنم."
    )

# ----------------------------
# 🧠 اجرای همزمان Flask و Bot
# ----------------------------
def main():
    if not BOT_TOKEN:
        raise RuntimeError("❌ BOT_TOKEN تعریف نشده!")

    # Flask برای UptimeRobot
    Thread(target=run_flask).start()

    # ربات تلگرام
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file))

    logger.info("🤖 OCR Bot started with Flask keep-alive ...")
    app.run_polling()

if __name__ == "__main__":
    main()
