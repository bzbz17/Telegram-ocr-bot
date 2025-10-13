import os
import tempfile
import logging
import re
from pathlib import Path

from flask import Flask
from threading import Thread

import pytesseract
from PIL import Image
from pdf2image import convert_from_path
import fitz  # PyMuPDF
import cv2
import numpy as np
import arabic_reshaper
from bidi.algorithm import get_display
import easyocr

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# ---------------- تنظیمات پایه ---------------- #
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
POPPLER_PATH = os.environ.get("POPPLER_PATH", "/usr/bin")

# Flask برای UptimeRobot
app = Flask(__name__)

@app.route("/")
def home():
    return "🤖 OCR Bot is alive and running!"

def run_flask():
    app.run(host="0.0.0.0", port=10000)

# ---------------- پردازش متن راست‌به‌چپ ---------------- #
def fix_rtl_text(text: str) -> str:
    """اصلاح ترتیب و شکل حروف فارسی و عربی برای نمایش درست در تلگرام"""
    try:
        text = re.sub(r'[^\S\r\n]+', ' ', text)  # حذف فاصله‌های اضافه
        reshaped = arabic_reshaper.reshape(text)
        bidi_text = get_display(reshaped)
        return bidi_text
    except Exception as e:
        logger.warning(f"RTL Fix error: {e}")
        return text

# ---------------- توابع OCR ---------------- #
def preprocess_image(img_path: str) -> Image.Image:
    """پیش‌پردازش تصویر برای OCR با حذف نویز، صاف‌سازی و سیاه‌سفید کردن"""
    img = cv2.imread(img_path, cv2.IMREAD_COLOR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.bilateralFilter(gray, 9, 75, 75)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    coords = np.column_stack(np.where(thresh > 0))
    if len(coords) > 0:
        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle
        (h, w) = gray.shape[:2]
        M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
        gray = cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    return Image.fromarray(gray)

def extract_text_tesseract(image: Image.Image, lang="fas+ara+eng") -> str:
    """استخراج متن با Tesseract"""
    config = "--oem 3 --psm 6"
    return pytesseract.image_to_string(image, lang=lang, config=config).strip()

def extract_text_easyocr(image_path: str, langs=["fa", "ar", "en"]) -> str:
    """استخراج متن با EasyOCR (فقط در صورت نیاز)"""
    reader = easyocr.Reader(langs, gpu=False)
    results = reader.readtext(image_path, detail=0, paragraph=True)
    return "\n".join(results).strip()

def extract_from_pdf(pdf_path: str) -> str:
    """استخراج متن از PDF (دیجیتال یا OCR)"""
    text = ""
    try:
        with fitz.open(pdf_path) as doc:
            for page in doc:
                text += page.get_text("text") + "\n"
    except Exception as e:
        logger.error(f"PDF read error: {e}")

    if text.strip():
        return fix_rtl_text(text.strip())

    # OCR اگر PDF تصویری بود
    images = convert_from_path(pdf_path, dpi=250, poppler_path=POPPLER_PATH)
    all_text = ""
    for img in images:
        tmp_img = tempfile.mktemp(suffix=".png")
        img.save(tmp_img, "PNG")
        processed = preprocess_image(tmp_img)
        ocr_text = extract_text_tesseract(processed)
        if len(ocr_text) < 20:
            logger.info("🧠 Switching to EasyOCR fallback...")
            ocr_text = extract_text_easyocr(tmp_img)
        all_text += "\n" + ocr_text
    return fix_rtl_text(all_text.strip())

def extract_from_image(image_path: str) -> str:
    """استخراج متن از عکس با fallback هوشمند"""
    processed = preprocess_image(image_path)
    text = extract_text_tesseract(processed)
    if len(text) < 20:
        logger.info("🧠 Switching to EasyOCR fallback...")
        text = extract_text_easyocr(image_path)
    return fix_rtl_text(text.strip())

# ---------------- هندلر ربات ---------------- #
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 سلام! من ربات استخراج متن هوشمندم.\n"
        "فقط کافیه عکس یا PDF بفرستی تا متن داخلش رو برات بیرون بکشم 🔍"
    )

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
        photo = message.photo[-1]
        file_id = photo.file_id
        file_name = f"{photo.file_unique_id}.jpg"

    tmp_dir = tempfile.mkdtemp()
    local_path = os.path.join(tmp_dir, file_name)

    try:
        telegram_file = await context.bot.get_file(file_id)
        await telegram_file.download_to_drive(custom_path=local_path)

        await message.reply_text("🕓 در حال پردازش و استخراج متن... لطفاً چند لحظه صبر کنید.")

        if file_name.lower().endswith(".pdf"):
            text = extract_from_pdf(local_path)
        else:
            text = extract_from_image(local_path)

        if not text.strip():
            await message.reply_text("⚠️ هیچ متنی پیدا نشد.")
            return

        # ارسال متن نهایی (در صورت طولانی بودن، بخش‌بخش)
        if len(text) > 4000:
            for i in range(0, len(text), 4000):
                await message.reply_text(text[i:i+4000])
        else:
            await message.reply_text(text)

    except Exception as e:
        logger.exception(f"Error: {e}")
        await message.reply_text(f"❌ خطا در پردازش فایل: {str(e)}")
    finally:
        try:
            for f in Path(tmp_dir).glob("*"):
                f.unlink(missing_ok=True)
            Path(tmp_dir).rmdir()
        except Exception:
            pass

# ---------------- اجرای ربات ---------------- #
def main():
    if not BOT_TOKEN:
        raise RuntimeError("❌ BOT_TOKEN is missing!")

    Thread(target=run_flask, daemon=True).start()

    app_tg = ApplicationBuilder().token(BOT_TOKEN).build()
    app_tg.add_handler(CommandHandler("start", start_cmd))
    app_tg.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file))

    logger.info("🤖 OCR Bot started successfully (RTL Fixed + Auto Fallback)...")
    app_tg.run_polling()

if __name__ == "__main__":
    main()
