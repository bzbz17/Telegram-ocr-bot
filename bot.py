import os
import io
import cv2
import numpy as np
import fitz  # PyMuPDF
import easyocr
from PIL import Image
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from hazm import Normalizer
import language_tool_python

# 🔹 تنظیم OCR فارسی + انگلیسی
reader = easyocr.Reader(['fa', 'en'])

# 🔹 ابزارهای اصلاح و نرمال‌سازی
normalizer = Normalizer()
tool = language_tool_python.LanguageTool('fa')

# 🔹 Flask برای uptime
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ OCR Telegram Bot is alive!"

# =============================
#      پردازش تصویر و PDF
# =============================
def preprocess_image(image_path):
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None
    img = cv2.resize(img, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
    img = cv2.fastNlMeansDenoising(img, None, 10, 7, 21)
    img = cv2.adaptiveThreshold(img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                cv2.THRESH_BINARY, 31, 2)
    return img

def extract_text_from_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text("text")
    if text.strip():
        return text  # PDF قابل کپی بود

    # در غیر این صورت، OCR
    for page_num in range(len(doc)):
        pix = doc.load_page(page_num).get_pixmap()
        img_data = Image.open(io.BytesIO(pix.tobytes("png")))
        img_path = f"temp_{page_num}.png"
        img_data.save(img_path)
        text += extract_text_from_image(img_path)
        os.remove(img_path)
    return text

def extract_text_from_image(image_path):
    processed = preprocess_image(image_path)
    if processed is None:
        return "❌ خطا در پردازش تصویر"
    result = reader.readtext(processed, detail=0, paragraph=True)
    text = " ".join(result)
    text = normalizer.normalize(text)
    matches = tool.check(text)
    text = language_tool_python.utils.correct(text, matches)
    return text

# =============================
#        Telegram Bot
# =============================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("سلام 👋\nفایل PDF یا تصویر را ارسال کنید تا متن استخراج شود.")

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await update.message.document.get_file() if update.message.document else await update.message.photo[-1].get_file()
    file_path = f"temp_{file.file_unique_id}.pdf" if file.file_path.endswith('.pdf') else f"temp_{file.file_unique_id}.jpg"
    await file.download_to_drive(file_path)

    if file_path.endswith(".pdf"):
        text = extract_text_from_pdf(file_path)
    else:
        text = extract_text_from_image(file_path)

    os.remove(file_path)

    if len(text) > 4000:
        for i in range(0, len(text), 4000):
            await update.message.reply_text(text[i:i+4000])
    else:
        await update.message.reply_text(text or "❌ متنی شناسایی نشد.")

def main():
    app_token = os.getenv("BOT_TOKEN")
    application = ApplicationBuilder().token(app_token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file))
    application.run_polling()

if __name__ == "__main__":
    from threading import Thread
    Thread(target=lambda: app.run(host="0.0.0.0", port=8080)).start()
    main()
