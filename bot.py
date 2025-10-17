import os
import cv2
import pytesseract
import easyocr
import numpy as np
import fitz  # PyMuPDF
from pdf2image import convert_from_path
from PIL import Image
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- تنظیم Flask برای UptimeRobot ---
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ OCR Telegram Bot is running!"

# --- تنظیم زبان‌ها برای OCR ---
reader = easyocr.Reader(['fa', 'ar', 'en'], gpu=False)
pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'

# --- پردازش تصویر برای OCR ---
def preprocess_image(image_path):
    img = cv2.imread(image_path)
    if img is None:
        return None
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.fastNlMeansDenoising(gray, None, 30, 7, 21)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return binary

# --- اجرای OCR با EasyOCR و Tesseract ---
def extract_text(image_path):
    img = preprocess_image(image_path)
    if img is None:
        return "❌ تصویر نامعتبر است."

    temp_path = "/tmp/processed_image.png"
    cv2.imwrite(temp_path, img)

    result_easy = reader.readtext(temp_path, detail=0, paragraph=True)
    result_tess = pytesseract.image_to_string(Image.open(temp_path), lang='fas+ara+eng')

    text = "\n".join(result_easy) + "\n" + result_tess

    # --- اصلاح ترتیب حروف فارسی (راست به چپ) ---
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    fixed_lines = []
    for line in lines:
        if any('\u0600' <= ch <= '\u06FF' for ch in line):  # اگر فارسی یا عربی است
            fixed_lines.append(line[::-1])
        else:
            fixed_lines.append(line)
    return "\n".join(fixed_lines)

# --- پردازش PDF ---
def process_pdf(pdf_path):
    images = convert_from_path(pdf_path, dpi=300)
    all_text = ""
    for i, img in enumerate(images):
        img_path = f"/tmp/page_{i}.png"
        img.save(img_path, "PNG")
        all_text += extract_text(img_path) + "\n\n"
    return all_text.strip()

# --- هندلر پیام‌ها در تلگرام ---
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await update.message.document.get_file()
    file_path = f"/tmp/{file.file_path.split('/')[-1]}"
    await file.download_to_drive(file_path)

    if file_path.lower().endswith('.pdf'):
        await update.message.reply_text("📄 در حال استخراج متن از PDF ... لطفاً چند لحظه صبر کنید.")
        text = process_pdf(file_path)
    else:
        await update.message.reply_text("🖼 در حال پردازش تصویر ...")
        text = extract_text(file_path)

    await update.message.reply_text("📝 نتیجه OCR:\n\n" + text[:4000])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 سلام! فایل تصویری یا PDF خودت رو بفرست تا متنش رو استخراج کنم.")

# --- اجرای ربات تلگرام ---
TOKEN = os.getenv("BOT_TOKEN")
app_telegram = ApplicationBuilder().token(TOKEN).build()
app_telegram.add_handler(CommandHandler("start", start))
app_telegram.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file))

import threading
threading.Thread(target=lambda: app_telegram.run_polling(allowed_updates=Update.ALL_TYPES)).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
