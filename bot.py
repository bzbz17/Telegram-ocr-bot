import os
import logging
import tempfile
from pathlib import Path
import re
from flask import Flask
import threading
import pytesseract
from PIL import Image
from pdf2image import convert_from_path
import fitz  # PyMuPDF
import cv2
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# ==================== تنظیمات اولیه ====================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
POPPLER_PATH = os.environ.get("POPPLER_PATH", "/usr/bin")

# ==================== سرور Flask برای UptimeRobot ====================
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Bot is running and awake!"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

# ==================== تابع تشخیص زبان ====================
def detect_language(image: Image.Image) -> str:
    """تشخیص خودکار زبان (فارسی، عربی یا انگلیسی)"""
    preview_text = pytesseract.image_to_string(image, lang="fas+ara+eng", config="--psm 6")
    fa = len(re.findall(r'[\u0600-\u06FF]', preview_text))
    ar = len(re.findall(r'[\u0621-\u064A]', preview_text))
    en = len(re.findall(r'[A-Za-z]', preview_text))
    if fa + ar > en:
        return "fas+ara"
    else:
        return "eng"

# ==================== بهبود کیفیت تصویر ====================
def preprocess_image(image_path: str):
    """بهبود تصویر برای افزایش دقت OCR"""
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    img = cv2.bilateralFilter(img, 9, 75, 75)
    _, img = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    temp_path = image_path.replace(".jpg", "_clean.jpg")
    cv2.imwrite(temp_path, img)
    return temp_path

# ==================== استخراج متن از PDF ====================
def extract_text_from_pdf(pdf_path: str):
    """OCR و استخراج از PDF"""
    try:
        text = ""
        with fitz.open(pdf_path) as doc:
            for page in doc:
                content = page.get_text("text")
                if content.strip():
                    text += content + "\n"
        if text.strip():
            return text

        # اگر دیجیتال نبود، OCR از تصویر صفحات
        images = convert_from_path(pdf_path, dpi=250, poppler_path=POPPLER_PATH)
        result = []
        for img in images:
            tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
            img.save(tmp.name, "JPEG")
            clean = preprocess_image(tmp.name)
            lang = detect_language(Image.open(clean))
            t = pytesseract.image_to_string(Image.open(clean), lang=lang)
            result.append(t)
        return "\n".join(result)
    except Exception as e:
        logger.error(f"PDF OCR error: {e}")
        return ""

# ==================== استخراج متن از تصویر ====================
def extract_text_from_image(image_path: str):
    """OCR از تصویر"""
    clean = preprocess_image(image_path)
    lang = detect_language(Image.open(clean))
    text = pytesseract.image_to_string(Image.open(clean), lang=lang)
    return text.strip()

# ==================== هندلرها ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 سلام! من ربات استخراج متن هستم.\n\n"
        "📄 فقط کافیه یه فایل PDF یا عکس بفرستی تا متن فارسی، عربی یا انگلیسی رو برات نمایش بدم ✅"
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

    await message.reply_text("⏳ در حال پردازش فایل، لطفاً کمی صبر کنید...")

    try:
        if file_name.lower().endswith(".pdf"):
            text = extract_text_from_pdf(local_path)
        else:
            text = extract_text_from_image(local_path)

        if not text.strip():
            await message.reply_text("⚠️ متنی یافت نشد.")
        else:
            # تصحیح راست به چپ فارسی و عربی
            fixed = text.replace("\n", " ").strip()
            await message.reply_text(f"📝 متن استخراج‌شده:\n\n{fixed}")

    except Exception as e:
        logger.exception(f"Error while processing file: {e}")
        await message.reply_text(f"❌ خطا در پردازش فایل: {str(e)}")

# ==================== اجرای ربات ====================
def main():
    # اجرای Flask برای UptimeRobot
    threading.Thread(target=run_flask).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file))

    logger.info("🤖 Bot is running and Flask server active...")
    app.run_polling()

if __name__ == "__main__":
    main()
