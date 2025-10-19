import os
import logging
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import easyocr
import fitz  # PyMuPDF
from pdf2image import convert_from_path
from hazm import Normalizer
import numpy as np
import cv2
from PIL import Image
import tempfile

# --- Logging ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# --- Flask server for uptime ---
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 OCR Bot is alive!", 200

# --- Initialize OCR ---
reader = easyocr.Reader(['fa', 'ar', 'en'])
normalizer = Normalizer()

# --- Telegram bot setup ---
BOT_TOKEN = os.getenv("BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ ربات OCR فارسی فعال است!\nلطفاً فایل PDF یا عکس ارسال کنید.")

def preprocess_image(image_path):
    """پیش‌پردازش تصویر برای دقت بالاتر OCR"""
    img = cv2.imread(image_path, cv2.IMREAD_COLOR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.medianBlur(gray, 3)
    thresh = cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 2)
    return thresh

def perform_ocr(image_path):
    processed = preprocess_image(image_path)
    temp_path = tempfile.mktemp(suffix=".png")
    cv2.imwrite(temp_path, processed)
    result = reader.readtext(temp_path, detail=0)
    text = "\n".join(result)
    return normalizer.normalize(text)

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await update.message.document.get_file() if update.message.document else await update.message.photo[-1].get_file()
    file_path = f"temp_{update.message.from_user.id}.pdf"
    await file.download_to_drive(file_path)

    extracted_text = ""

    if file_path.endswith(".pdf"):
        images = convert_from_path(file_path)
        for img in images:
            temp_img = tempfile.mktemp(suffix=".png")
            img.save(temp_img, "PNG")
            extracted_text += perform_ocr(temp_img) + "\n"
    else:
        extracted_text = perform_ocr(file_path)

    if not extracted_text.strip():
        await update.message.reply_text("❌ متنی شناسایی نشد. لطفاً فایل واضح‌تر بفرستید.")
    else:
        await update.message.reply_text(f"📄 متن استخراج‌شده:\n\n{extracted_text}")

def main():
    app_tg = ApplicationBuilder().token(BOT_TOKEN).build()
    app_tg.add_handler(CommandHandler("start", start))
    app_tg.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file))

    import threading
    threading.Thread(target=lambda: app_tg.run_polling(allowed_updates=Update.ALL_TYPES)).start()

    app.run(host="0.0.0.0", port=8080)

if __name__ == "__main__":
    main()
