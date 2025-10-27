import os
import cv2
import pytesseract
from pytesseract import Output
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from threading import Thread
from hazm import Normalizer

# 🔹 تنظیم OCR فارسی + عربی
pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"
tess_config = r'--oem 3 --psm 6 -l fas+ara'

# 🔹 آماده‌سازی Flask برای UptimeRobot
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Telegram OCR Bot is alive!"

# 🔹 پیش‌پردازش تصویر
def preprocess_image(image_path):
    image = cv2.imread(image_path)
    if image is None:
        return None
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
    gray = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                 cv2.THRESH_BINARY, 31, 2)
    gray = cv2.fastNlMeansDenoising(gray, h=10)
    return gray

# 🔹 استخراج متن از تصویر یا PDF
def extract_text(file_path):
    import fitz  # PyMuPDF
    text_output = ""
    if file_path.lower().endswith(".pdf"):
        doc = fitz.open(file_path)
        for page in doc:
            pix = page.get_pixmap(dpi=300)
            img_path = f"/tmp/page_{page.number}.png"
            pix.save(img_path)
            pre_img = preprocess_image(img_path)
            if pre_img is not None:
                text_output += pytesseract.image_to_string(pre_img, config=tess_config)
            os.remove(img_path)
    else:
        pre_img = preprocess_image(file_path)
        if pre_img is not None:
            text_output = pytesseract.image_to_string(pre_img, config=tess_config)

    # 🔹 نرمال‌سازی فارسی (اصلاح فاصله و نویسه‌ها)
    normalizer = Normalizer()
    normalized_text = normalizer.normalize(text_output)

    # 🔹 اصلاح جهت نمایش راست‌به‌چپ
    fixed_text = "\n".join([line.strip()[::-1] for line in normalized_text.split("\n") if line.strip()])

    return fixed_text or "❌ متنی شناسایی نشد."

# 🔹 هندل پیام‌ها در تلگرام
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = None
    if update.message.document:
        file = await update.message.document.get_file()
    elif update.message.photo:
        file = await update.message.photo[-1].get_file()
    else:
        await update.message.reply_text("📎 لطفاً فایل PDF یا عکس ارسال کنید.")
        return

    file_path = f"/tmp/{os.path.basename(file.file_path)}"
    await file.download_to_drive(file_path)

    await update.message.reply_text("⏳ در حال پردازش OCR... لطفاً منتظر بمانید.")

    text = extract_text(file_path)
    await update.message.reply_text(f"📄 نتیجه OCR:\n\n{text}")

    os.remove(file_path)

# 🔹 اجرای ربات
def run_bot():
    TOKEN = os.getenv("BOT_TOKEN")
    if not TOKEN:
        raise ValueError("❌ BOT_TOKEN environment variable not set!")
    app_tg = ApplicationBuilder().token(TOKEN).build()
    app_tg.add_handler(MessageHandler(filters.ALL, handle_message))
    app_tg.run_polling(allowed_updates=Update.ALL_TYPES)

# 🔹 اجرای موازی Flask + Telegram
if __name__ == "__main__":
    Thread(target=run_bot, daemon=True).start()
    app.run(host="0.0.0.0", port=8080)
