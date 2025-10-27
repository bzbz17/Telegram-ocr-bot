import os
import io
import threading
import tempfile
from pathlib import Path
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from PIL import Image
import pytesseract
from pdf2image import convert_from_path
import cv2
import numpy as np
import logging
import fitz  # PyMuPDF

# ---------------------------------
# تنظیمات پایه
# ---------------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN")
POPPLER_PATH = os.environ.get("POPPLER_PATH", "/usr/bin")

if not BOT_TOKEN:
    raise RuntimeError("❌ BOT_TOKEN environment variable is missing!")

pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"
TESS_CONFIG = r'--oem 3 --psm 6'
TESS_LANG = "fas+ara+eng"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ocr-bot")

# ---------------------------------
# Flask App (برای UptimeRobot)
# ---------------------------------
app = Flask(__name__)

@app.route("/")
def home():
    return "✅ OCR Telegram Bot is running!"

# ---------------------------------
# توابع OCR
# ---------------------------------
def normalize_persian(text: str) -> str:
    if not text:
        return text
    text = text.replace("ي", "ی").replace("ك", "ک")
    text = text.replace("\u200c", " ")
    text = " ".join(text.split())
    return text.strip()

def preprocess_image(image_pil: Image.Image) -> np.ndarray:
    img = np.array(image_pil.convert("RGB"))[:, :, ::-1]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                 cv2.THRESH_BINARY, 31, 2)
    gray = cv2.fastNlMeansDenoising(gray, h=10)
    return gray

def ocr_image(image_pil: Image.Image) -> str:
    img = preprocess_image(image_pil)
    text = pytesseract.image_to_string(img, lang=TESS_LANG, config=TESS_CONFIG)
    return normalize_persian(text)

def ocr_pdf(path: str) -> str:
    try:
        doc = fitz.open(path)
        text_pages = [p.get_text("text") for p in doc]
        text = "\n".join(text_pages).strip()
        if text:
            return normalize_persian(text)
    except Exception:
        pass

    pages = convert_from_path(path, dpi=300, poppler_path=POPPLER_PATH)
    texts = [ocr_image(p) for p in pages]
    return "\n\n--- صفحه جدید ---\n\n".join(texts).strip()

# ---------------------------------
# هندلرهای تلگرام
# ---------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("سلام! فایل PDF یا عکس بفرست تا متنش رو برات استخراج کنم 📄")

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return

    if msg.document:
        file = await msg.document.get_file()
        fname = msg.document.file_name or "file.pdf"
    elif msg.photo:
        file = await msg.photo[-1].get_file()
        fname = f"{file.file_unique_id}.jpg"
    else:
        await msg.reply_text("لطفاً فقط عکس یا PDF بفرست.")
        return

    temp_dir = tempfile.mkdtemp()
    local_path = os.path.join(temp_dir, fname)
    await msg.reply_text("⏳ در حال پردازش...")
    await file.download_to_drive(custom_path=local_path)

    try:
        if fname.lower().endswith(".pdf"):
            text = ocr_pdf(local_path)
        else:
            image = Image.open(local_path)
            text = ocr_image(image)

        if not text.strip():
            await msg.reply_text("⚠️ متنی پیدا نشد. لطفاً تصویر واضح‌تر بفرست.")
        else:
            # ارسال در چند بخش اگر طولانی بود
            for i in range(0, len(text), 3500):
                await msg.reply_text(text[i:i + 3500])

    except Exception as e:
        logger.exception(e)
        await msg.reply_text(f"❌ خطا در OCR: {e}")
    finally:
        try:
            for f in Path(temp_dir).glob("*"):
                f.unlink(missing_ok=True)
            Path(temp_dir).rmdir()
        except Exception:
            pass

# ---------------------------------
# اجرای Flask و Bot هم‌زمان
# ---------------------------------
def run_flask():
    app.run(host="0.0.0.0", port=8080)

def run_bot():
    app_tg = ApplicationBuilder().token(BOT_TOKEN).build()
    app_tg.add_handler(CommandHandler("start", start))
    app_tg.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file))
    app_tg.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    # اجرای Flask در ترد جدا تا برنامه متوقف نشود
    threading.Thread(target=run_flask, daemon=True).start()
    # اجرای Bot در ترد اصلی
    run_bot()
