# =============================================================
# 🤖 bot.py — OCR فارسی، عربی و انگلیسی با دقت بالا (نسخه‌ی نهایی)
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
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
from pdf2image import convert_from_path
import fitz  # PyMuPDF
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# ----------------------------
# تنظیمات پایه
# ----------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
POPPLER_PATH = os.environ.get("POPPLER_PATH", "/usr/bin")

MAX_WORKERS = int(os.environ.get("OCR_MAX_WORKERS", "4"))
executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

# تنظیمات دقیق Tesseract برای حفظ فاصله‌ها و دقت بالا
OCR_CONFIG = "--oem 3 --psm 6 -c preserve_interword_spaces=1"


# ----------------------------
# 🧩 پیش‌پردازش هوشمند تصویر
# ----------------------------
def preprocess_image_for_ocr(img: Image.Image) -> Image.Image:
    """
    بهینه‌سازی تصویر برای افزایش دقت OCR:
    - تبدیل به سیاه‌وسفید
    - حذف نویز و افزایش وضوح
    - آستانه‌گذاری برای وضوح حروف
    """
    try:
        img = img.convert("L")  # خاکستری
        if img.width < 1200:
            scale = 1200 / img.width
            img = img.resize((int(img.width * scale), int(img.height * scale)), Image.Resampling.LANCZOS)

        img = ImageOps.autocontrast(img, cutoff=2)
        img = ImageEnhance.Sharpness(img).enhance(2.0)
        img = ImageEnhance.Contrast(img).enhance(1.6)
        img = img.filter(ImageFilter.MedianFilter(size=3))
        img = img.point(lambda x: 255 if x > 160 else 0, mode="1")
        return img
    except Exception as e:
        logger.error(f"Preprocess error: {e}")
        return img


# ----------------------------
# 🌐 تشخیص زبان غالب تصویر
# ----------------------------
def detect_language(image: Image.Image) -> str:
    """تشخیص خودکار فارسی، عربی یا انگلیسی"""
    try:
        txt = pytesseract.image_to_string(image, lang="fas+ara+eng", config="--psm 6")
        farsi = len(re.findall(r'[\u0600-\u06FF]', txt))
        arabic = len(re.findall(r'[\u0750-\u077F]', txt))
        english = len(re.findall(r'[A-Za-z]', txt))
        if farsi > english and farsi >= arabic:
            return "fas"
        elif arabic > english and arabic > farsi:
            return "ara"
        elif english > farsi and english > arabic:
            return "eng"
        else:
            return "fas+eng+ara"
    except Exception:
        return "fas+eng+ara"


# ----------------------------
# 🧠 OCR از تصویر با بازسازی راست‌به‌چپ
# ----------------------------
def ocr_image_to_text(img: Image.Image, lang: str) -> str:
    """اجرای OCR با حفظ چیدمان فارسی و فاصله بین کلمات"""
    try:
        processed = preprocess_image_for_ocr(img)
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
    except Exception as e:
        logger.error(f"OCR image error: {e}")
        return ""


# ----------------------------
# 📄 OCR از PDF (چند صفحه‌ای)
# ----------------------------
def ocr_pdf_to_text(pdf_path: str, poppler_path: Optional[str] = None) -> str:
    """تبدیل PDF به متن با OCR چند‌صفحه‌ای"""
    try:
        images = convert_from_path(pdf_path, dpi=300, poppler_path=poppler_path)
    except Exception as e:
        logger.error(f"PDF to image error: {e}")
        return ""

    def process_page(img):
        lang = detect_language(img)
        return ocr_image_to_text(img, lang)

    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(images))) as pool:
        results = pool.map(process_page, images)

    return "\n\n".join(results).strip()


# ----------------------------
# 📨 هندل فایل‌ها از تلگرام
# ----------------------------
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    # گرفتن فایل
    if message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name or "file.pdf"
    elif message.photo:
        file_id = message.photo[-1].file_id
        file_name = f"{message.photo[-1].file_unique_id}.jpg"
    else:
        await message.reply_text("📄 لطفاً یک فایل PDF یا عکس بفرست.")
        return

    tmp_dir = tempfile.mkdtemp()
    local_path = os.path.join(tmp_dir, file_name)

    try:
        file = await context.bot.get_file(file_id)
        await file.download_to_drive(custom_path=local_path)
        await message.reply_text("⏳ در حال پردازش و استخراج متن ...")

        def process():
            if file_name.lower().endswith(".pdf"):
                return ocr_pdf_to_text(local_path, poppler_path=POPPLER_PATH)
            else:
                img = Image.open(local_path)
                lang = detect_language(img)
                return ocr_image_to_text(img, lang)

        loop = asyncio.get_running_loop()
        text = await loop.run_in_executor(executor, process)

        if not text.strip():
            await message.reply_text("⚠️ متنی پیدا نشد.")
            return

        # تقسیم پیام برای تلگرام
        for i in range(0, len(text), 4000):
            await message.reply_text(text[i:i + 4000])

        await message.reply_text("✅ استخراج متن انجام شد.")
    except Exception as e:
        logger.exception(e)
        await message.reply_text(f"❌ خطا: {str(e)}")
    finally:
        for f in Path(tmp_dir).glob("*"):
            f.unlink(missing_ok=True)
        Path(tmp_dir).rmdir()


# ----------------------------
# 🚀 فرمان شروع
# ----------------------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 سلام!\nمن ربات OCR فارسی هستم.\n"
        "فایل PDF یا عکس بفرست تا متن فارسی، عربی یا انگلیسی رو برات استخراج کنم."
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

    logger.info("🤖 OCR Bot started successfully ...")
    app.run_polling()


if __name__ == "__main__":
    main()
