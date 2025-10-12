# =============================================================
# 🤖 bot.py — OCR هوشمند فارسی/انگلیسی با تشخیص دست‌نویس یا تایپ‌شده
# =============================================================

import os
import tempfile
import logging
import re
import asyncio
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import pytesseract
import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageOps
from pdf2image import convert_from_path
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# ----------------------------
# تنظیمات عمومی
# ----------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
POPPLER_PATH = os.environ.get("POPPLER_PATH", "/usr/bin")

MAX_WORKERS = int(os.environ.get("OCR_MAX_WORKERS", "6"))
executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

# تنظیمات OCR پایه (دقت بالا + فاصله صحیح)
OCR_CONFIG = "--oem 3 --psm 6 -c preserve_interword_spaces=1 --tessdata-dir /usr/share/tesseract-ocr/4.00/tessdata"


# ----------------------------
# 🧠 تابع تشخیص دست‌نویس یا تایپ‌شده
# ----------------------------
def detect_handwritten(image: np.ndarray) -> bool:
    """
    بررسی می‌کند که آیا تصویر بیشتر دست‌نویس است یا چاپی.
    مبنا: تراکم لبه‌ها و شکل حروف.
    """
    try:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)
        density = np.sum(edges > 0) / edges.size

        # اگر تراکم خطوط بالا باشد، احتمال دست‌نویس بودن بیشتر است.
        return density > 0.05
    except Exception as e:
        logger.error(f"Handwriting detection error: {e}")
        return False


# ----------------------------
# 🧩 پیش‌پردازش تصویر
# ----------------------------
def preprocess_image(img: Image.Image, handwritten: bool = False) -> Image.Image:
    """بهینه‌سازی تصویر برای OCR، بسته به نوع متن"""
    img = img.convert("L")
    if img.width < 1000:
        scale = 1000 / img.width
        img = img.resize((int(img.width * scale), int(img.height * scale)), Image.Resampling.LANCZOS)
    img = ImageOps.autocontrast(img, cutoff=2)

    if handwritten:
        # برای متن دست‌نویس: افزایش شدت و حذف سایه
        img = ImageEnhance.Contrast(img).enhance(2.0)
        img = ImageEnhance.Sharpness(img).enhance(1.8)
    else:
        # برای متن تایپ‌شده: صاف و شفاف‌تر
        img = ImageEnhance.Contrast(img).enhance(1.4)
        img = ImageEnhance.Sharpness(img).enhance(1.2)

    img = img.point(lambda x: 255 if x > 160 else 0, mode="1")
    return img


# ----------------------------
# 🌐 تشخیص زبان
# ----------------------------
def detect_language(image: Image.Image) -> str:
    """تشخیص سریع زبان غالب"""
    try:
        txt = pytesseract.image_to_string(image, lang="fas+eng", config="--psm 6")
        farsi = len(re.findall(r'[\u0600-\u06FF]', txt))
        english = len(re.findall(r'[A-Za-z]', txt))
        return "fas_fast+eng" if farsi > english else "eng"
    except Exception:
        return "fas_fast+eng"


# ----------------------------
# 🔍 OCR روی تصویر
# ----------------------------
def ocr_image_to_text(img: Image.Image, lang: str, handwritten: bool) -> str:
    """اجرای OCR با بازسازی فاصله بین کلمات"""
    processed = preprocess_image(img, handwritten)
    data = pytesseract.image_to_data(
        processed, lang=lang, config=OCR_CONFIG, output_type=pytesseract.Output.DICT
    )

    lines = {}
    for i, text in enumerate(data["text"]):
        if not text.strip():
            continue
        y = data["top"][i]
        line_key = round(y / 40)
        lines.setdefault(line_key, []).append((data["left"][i], text))

    full_text = []
    for _, words in sorted(lines.items()):
        words = sorted(words, key=lambda x: x[0], reverse=True)
        line = " ".join(w for _, w in words)
        full_text.append(line)

    text = "\n".join(full_text).strip()
    text = text.replace("ي", "ی").replace("ك", "ک")
    return text


# ----------------------------
# 📄 OCR PDF چند صفحه‌ای
# ----------------------------
def ocr_pdf_to_text(pdf_path: str, poppler_path: Optional[str] = None) -> str:
    """تبدیل PDF به متن OCR با تشخیص نوع متن (دست‌نویس/تایپ‌شده)"""
    images = convert_from_path(pdf_path, dpi=200, poppler_path=poppler_path)
    results = []

    for img in images:
        np_img = np.array(img)
        handwritten = detect_handwritten(np_img)
        lang = detect_language(img)
        text = ocr_image_to_text(img, lang, handwritten)
        results.append(text)

    return "\n\n".join(results).strip()


# ----------------------------
# 📨 دریافت فایل از تلگرام
# ----------------------------
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return

    if msg.document:
        file_id = msg.document.file_id
        file_name = msg.document.file_name or "file.pdf"
    elif msg.photo:
        file_id = msg.photo[-1].file_id
        file_name = f"{msg.photo[-1].file_unique_id}.jpg"
    else:
        await msg.reply_text("📄 لطفاً یک فایل PDF یا عکس بفرست.")
        return

    tmp_dir = tempfile.mkdtemp()
    local_path = os.path.join(tmp_dir, file_name)

    try:
        file = await context.bot.get_file(file_id)
        await file.download_to_drive(custom_path=local_path)
        await msg.reply_text("⏳ در حال پردازش هوشمند تصویر و تشخیص نوع متن ...")

        def process():
            if file_name.lower().endswith(".pdf"):
                return ocr_pdf_to_text(local_path, poppler_path=POPPLER_PATH)
            else:
                img = Image.open(local_path)
                np_img = np.array(img)
                handwritten = detect_handwritten(np_img)
                lang = detect_language(img)
                return ocr_image_to_text(img, lang, handwritten)

        loop = asyncio.get_running_loop()
        text = await loop.run_in_executor(executor, process)

        if not text.strip():
            await msg.reply_text("⚠️ متنی پیدا نشد.")
            return

        for i in range(0, len(text), 4000):
            await msg.reply_text(text[i:i + 4000])

        await msg.reply_text("✅ استخراج متن هوشمند انجام شد.")
    except Exception as e:
        logger.exception(e)
        await msg.reply_text(f"❌ خطا در پردازش: {str(e)}")
    finally:
        for f in Path(tmp_dir).glob("*"):
            f.unlink(missing_ok=True)
        Path(tmp_dir).rmdir()


# ----------------------------
# 🚀 فرمان شروع
# ----------------------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 سلام!\n"
        "من ربات OCR هوشمند هستم 📑\n"
        "فایل PDF یا عکس بفرست تا تشخیص بدم تایپ‌شده‌ست یا دست‌نویس و متنش رو با دقت بالا برات استخراج کنم 💪"
    )


# ----------------------------
# 🧠 اجرای اصلی
# ----------------------------
def main():
    if not BOT_TOKEN:
        raise RuntimeError("❌ BOT_TOKEN تعریف نشده!")

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file))

    logger.info("🤖 Smart OCR Bot started successfully ...")
    app.run_polling()


if __name__ == "__main__":
    main()
