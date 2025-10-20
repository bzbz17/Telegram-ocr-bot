import os
import io
import cv2
import pytesseract
import numpy as np
import pdf2image
import fitz  # PyMuPDF
from flask import Flask
from hazm import Normalizer
from PIL import Image
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CommandHandler

# ==============================
# تنظیمات اولیه
# ==============================
BOT_TOKEN = os.getenv("BOT_TOKEN")
pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"

app = Flask(__name__)
normalizer = Normalizer()

# ==============================
# توابع کمکی OCR
# ==============================
def preprocess_image(image):
    """پیش‌پردازش تصویر برای بهبود OCR"""
    gray = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
    gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    gray = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                 cv2.THRESH_BINARY, 31, 2)
    gray = cv2.fastNlMeansDenoising(gray, None, 30, 7, 21)
    return gray

def extract_text_from_image(image):
    """استخراج متن از تصویر با Tesseract"""
    processed = preprocess_image(image)
    text = pytesseract.image_to_string(processed, lang="fas+ara+eng", config="--psm 6")
    text = normalizer.normalize(text)
    # راست به چپ کردن متون فارسی و عربی
    lines = [line.strip()[::-1] if any('آ' <= ch <= 'ی' for ch in line) else line for line in text.splitlines()]
    return "\n".join(lines)

def extract_text_from_pdf(file_path):
    """استخراج متن از PDF (در صورت وجود متن مستقیماً، در غیر این صورت OCR)"""
    text = ""
    try:
        with fitz.open(file_path) as doc:
            for page in doc:
                page_text = page.get_text("text")
                if page_text.strip():
                    text += page_text + "\n"
    except Exception:
        pass

    if not text.strip():
        images = pdf2image.convert_from_path(file_path, dpi=300)
        for img in images:
            text += extract_text_from_image(img) + "\n"

    return text.strip()

# ==============================
# هندلرهای تلگرام
# ==============================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 سلام! فایل PDF یا عکس خود را بفرست تا متنش را برات استخراج کنم.")

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await update.message.document.get_file()
    file_path = f"/tmp/{file.file_unique_id}.pdf"
    await file.download_to_drive(file_path)

    await update.message.reply_text("🔍 در حال پردازش فایل، لطفاً کمی صبر کنید...")

    text = extract_text_from_pdf(file_path)

    if text:
        await update.message.reply_text(f"📄 متن استخراج‌شده:\n\n{text[:4000]}")
    else:
        await update.message.reply_text("❌ متنی یافت نشد. لطفاً از وضوح تصویر یا فایل دیگری استفاده کنید.")

    os.remove(file_path)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = await update.message.photo[-1].get_file()
    image_bytes = await photo.download_as_bytearray()
    image = Image.open(io.BytesIO(image_bytes))

    await update.message.reply_text("🔍 در حال پردازش تصویر، لطفاً صبر کنید...")

    text = extract_text_from_image(image)

    if text:
        await update.message.reply_text(f"🖼 متن استخراج‌شده:\n\n{text[:4000]}")
    else:
        await update.message.reply_text("❌ متنی در تصویر یافت نشد.")

# ==============================
# راه‌اندازی ربات
# ==============================
def run_bot():
    app_tg = Application.builder().token(BOT_TOKEN).build()
    app_tg.add_handler(CommandHandler("start", start))
    app_tg.add_handler(MessageHandler(filters.Document.PDF, handle_file))
    app_tg.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    app_tg.run_polling(allowed_updates=Update.ALL_TYPES)

# ==============================
# Flask برای UptimeRobot
# ==============================
@app.route("/")
def home():
    return "🤖 OCR Bot is running!"

if __name__ == "__main__":
    import threading
    t = threading.Thread(target=run_bot)
    t.start()
    app.run(host="0.0.0.0", port=8080)
