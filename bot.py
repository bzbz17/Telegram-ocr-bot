# bot.py
import os
import io
import asyncio
import logging
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

# -----------------------
# تنظیمات پایه
# -----------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN")
POPPLER_PATH = os.environ.get("POPPLER_PATH", "/usr/bin")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN env var is required")

# tesseract path (در اکثر ایمیج‌ها همین است)
pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"

# پیکربندی tesseract: OEM 3 + PSM 6؛ زبان‌ها: فارسی، عربی، انگلیسی
TESS_CONFIG = r'--oem 3 --psm 6'
TESS_LANG = "fas+ara+eng"

# logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ocr-bot")

# -----------------------
# Flask (برای UptimeRobot)
# -----------------------
app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Telegram OCR Bot is alive and running!"

# -----------------------
# توابع کمکی OCR و پیش‌پردازش
# -----------------------
def simple_normalize_persian(text: str) -> str:
    """تعدادی تبدیل ساده برای فارسی/عربی تا نیازی به hazm نباشد."""
    if not text:
        return text
    # تبدیل ی عربی -> ی فارسی و ک عربی -> ک فارسی
    text = text.replace("ي", "ی").replace("ك", "ک")
    # حذف کاراکترهای زائد یونیکد
    text = text.replace("\u200c", " ")  # نیم‌فاصله -> space (در صورت نیاز میشه برعکس کرد)
    # فشرده‌سازی فاصله‌های اضافی
    text = " ".join(text.split())
    return text.strip()

def preprocess_image_cv(image_pil: Image.Image) -> np.ndarray:
    """پیش‌پردازش ساده با OpenCV: grayscale, resize, adaptive threshold, denoise"""
    img = np.array(image_pil.convert("RGB"))[:, :, ::-1]  # RGB->BGR
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # افزایش اندازه برای خوانایی بهتر (بسته به کیفیت میشه تنظیم کرد)
    h, w = gray.shape
    scale = 1.5 if max(h, w) < 2000 else 1.0
    if scale != 1.0:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    # adaptive threshold
    gray = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                 cv2.THRESH_BINARY, 31, 2)
    # denoise
    gray = cv2.fastNlMeansDenoising(gray, h=10)
    return gray

def ocr_image_from_pil(image_pil: Image.Image) -> str:
    proc = preprocess_image_cv(image_pil)
    # pytesseract accepts numpy array
    text = pytesseract.image_to_string(proc, lang=TESS_LANG, config=TESS_CONFIG)
    return simple_normalize_persian(text)

def ocr_pdf_file(pdf_path: str) -> str:
    text_parts = []
    try:
        pages = convert_from_path(pdf_path, dpi=300, poppler_path=POPPLER_PATH)
    except Exception as e:
        logger.error("pdf->image conversion failed: %s", e)
        return ""
    for page in pages:
        txt = ocr_image_from_pil(page)
        if txt:
            text_parts.append(txt)
    return "\n\n--- صفحه جدید ---\n\n".join(text_parts).strip()

def extract_text_from_pdf_direct(pdf_path: str) -> str:
    """سعی می‌کنیم اول متن دیجیتال را از PDF بگیریم با PyMuPDF"""
    try:
        import fitz
        doc = fitz.open(pdf_path)
        parts = []
        for p in doc:
            t = p.get_text("text")
            if t and t.strip():
                parts.append(t)
        return "\n".join(parts).strip()
    except Exception as e:
        logger.debug("direct pdf text extraction failed: %s", e)
        return ""

# -----------------------
# هندلرهای تلگرام
# -----------------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "سلام! من ربات OCR هستم. فایل PDF یا عکس بفرست تا متنش را برات استخراج کنم."
    )

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return

    # تعیین فایل (doc یا photo)
    if msg.document:
        file_obj = await msg.document.get_file()
        fname = msg.document.file_name or f"{file_obj.file_id}.pdf"
    elif msg.photo:
        file_obj = await msg.photo[-1].get_file()
        fname = f"{file_obj.file_unique_id}.jpg"
    else:
        await msg.reply_text("لطفاً یک فایل PDF یا تصویر ارسال کنید.")
        return

    tmp_dir = tempfile.mkdtemp()
    local_path = os.path.join(tmp_dir, fname)
    try:
        await file_obj.download_to_drive(custom_path=local_path)
        await msg.reply_text("⏳ در حال پردازش؛ کمی صبر کنید...")

        text = ""
        if fname.lower().endswith(".pdf"):
            # ابتدا تلاش برای استخراج متن دیجیتال
            text = extract_text_from_pdf_direct(local_path)
            if not text.strip():
                text = ocr_pdf_file(local_path)
        else:
            # عکس
            pil_img = Image.open(local_path)
            text = ocr_image_from_pil(pil_img)

        if not text.strip():
            await msg.reply_text("⚠️ متنی یافت نشد. کیفیت/وضوح تصویر را افزایش دهید.")
            return

        # اگر خیلی طولانی است، آن را به بخش‌های 3500 حرفی تقسیم کن
        chunk_size = 3500
        for i in range(0, len(text), chunk_size):
            await msg.reply_text(text[i:i+chunk_size])

    except Exception as e:
        logger.exception("error processing file: %s", e)
        await msg.reply_text(f"❌ خطا در پردازش فایل: {e}")
    finally:
        # پاکسازی
        try:
            for f in Path(tmp_dir).glob("*"):
                f.unlink(missing_ok=True)
            Path(tmp_dir).rmdir()
        except Exception:
            pass

# -----------------------
# اجرای همزمان Flask + Bot در یک event loop
# -----------------------
async def run_flask():
    loop = asyncio.get_event_loop()
    # اجرای Flask به صورت blocking در executor تا داخل loop بماند
    await loop.run_in_executor(None, lambda: app.run(host="0.0.0.0", port=8080))

async def run_bot():
    app_tg = ApplicationBuilder().token(BOT_TOKEN).build()
    app_tg.add_handler(CommandHandler("start", start_cmd))
    app_tg.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file))
    # run_polling is a coroutine — stop_signals=None to avoid signal handlers in non-main contexts
    await app_tg.run_polling(stop_signals=None, allowed_updates=Update.ALL_TYPES)

async def main():
    # run both concurrently
    await asyncio.gather(run_flask(), run_bot())

if __name__ == "__main__":
    # اجرا با asyncio.run (یک event loop اصلی)
    asyncio.run(main())
