import os
import cv2
import pytesseract
import numpy as np
import fitz  # PyMuPDF
from pdf2image import convert_from_path
from PIL import Image
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import threading

# --- Flask برای UptimeRobot ---
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Telegram OCR Bot is running!"

# --- پردازش تصویر ---
def preprocess_image(image_path):
    img = cv2.imread(image_path)
    if img is None:
        return None
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.fastNlMeansDenoising(gray, None, 30, 7, 21)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return binary

# --- استخراج متن ---
def extract_text(image_path):
    img = preprocess_image(image_path)
    if img is None:
        return "❌ تصویر معتبر نیست."

    temp_path = "/tmp/ocr.png"
    cv2.imwrite(temp_path, img)

    # فقط pytesseract (سبک‌تر)
    text = pytesseract.image_to_string(Image.open(temp_path), lang='fas+ara+eng')

    # اصلاح راست‌به‌چپ
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    fixed = []
    for line in lines:
        if any('\u0600' <= ch <= '\u06FF' for ch in line):
            fixed.append(line[::-1])
        else:
            fixed.append(line)
    return "\n".join(fixed)

# --- PDF ---
def process_pdf(pdf_path):
    images = convert_from_path(pdf_path, dpi=250)
    all_text = ""
    for i, img in enumerate(images):
        path = f"/tmp/page_{i}.png"
        img.save(path, "PNG")
        all_text += extract_text(path) + "\n\n"
    return all_text.strip()

# --- ربات تلگرام ---
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await update.message.document.get_file()
    file_path = f"/tmp/{file.file_path.split('/')[-1]}"
    await file.download_to_drive(file_path)

    if file_path.lower().endswith('.pdf'):
        await update.message.reply_text("📄 در حال پردازش PDF...")
        text = process_pdf(file_path)
    else:
        await update.message.reply_text("🖼 در حال OCR تصویر...")
        text = extract_text(file_path)

    await update.message.reply_text("📝 نتیجه:\n\n" + text[:4000])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 سلام! لطفاً فایل PDF یا تصویر خود را بفرست.")

TOKEN = os.getenv("BOT_TOKEN")
telegram_app = ApplicationBuilder().token(TOKEN).build()
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file))

# اجرای هم‌زمان Flask و ربات
threading.Thread(target=lambda: telegram_app.run_polling(allowed_updates=Update.ALL_TYPES)).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
