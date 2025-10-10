# =============================================================
# 🤖 bot.py — OCR سریع و دقیق فارسی، عربی و انگلیسی (نسخه‌ی بهینه)
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
# 🧩 تنظیمات پایه
# ----------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
POPPLER_PATH = os.environ.get("POPPLER_PATH", "/usr/bin")

# استفاده از چند هسته برای OCR هم‌زمان
MAX_WORKERS = int(os.environ.get("OCR_MAX_WORKERS", "6"))
executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

# 🔧 تنظیمات OCR برای سرعت و دقت
OCR_CONFIG = "--oem 3 --psm 6 -c preserve_interword_spaces=1 --tessdata-dir /usr/share/tesseract-ocr/4.00/tessdata"


# ----------------------------
# 🧠 پیش‌پردازش سبک تصویر برای OCR
# ----------------------------
def preprocess_image_for_ocr(img: Image.Image) -> Image.Image:
    """
    بهینه‌سازی تصویر برای افزایش دقت OCR با حداقل هزینه‌ی زمانی:
    - خاکستری، افزایش وضوح و کنتراست
    - حذف نویز سنگین غیرفعال برای سرعت بیشتر
    """
    try:
        img = img.convert("L")
        if img.width < 1000:
            scale = 1000 / img.width
            img = img.resize((int(img.width * scale), int(img.height * scale)), Image.Resampling.LANCZOS)

        img = ImageOps.autocontrast(img, cutoff=2)
        img = ImageEnhance.Sharpness(img).enhance(1.5)
        img = ImageEnhance.Contrast(img).enhance(1.4)
        # حذف MedianFilter برای سرعت بیشتر
        img = img.point(lambda x: 255 if x > 160 else 0, mode="1")
        return img
    except Exception as e:
        logger.error(f"Preprocess error: {e}")
        return img


# ----------------------------
# 🌐 تشخیص زبان متن در تصویر
# ----------------------------
def detect_language(image: Image.Image) -> str:
    """تشخیص سریع فارسی یا انگلیسی"""
    try:
        txt = pytesseract.image_to_string(image, lang="fas+eng", config="--psm 6")
        farsi = len(re.findall(r'[\u0600-\u06FF]', txt))
        english = len(re.findall(r'[A-Za-z]', txt))
        if farsi > english:
            return "fas_fast+eng"
        else:
            return "eng"
    except Exception:
        return "fas_fast+eng"


# ----------------------------
# 🔍 OCR تصویر با حفظ راست‌به‌چپ
# ----------------------------
def ocr_image_to_text(img: Image.Image, lang: str) -> str:
    """اجرای OCR با بازسازی فاصله بین کلمات"""
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
# 📄 OCR PDF با سرعت بالا (DPI کمتر)
# ----------------------------
def ocr_pdf_to_text(pdf_path: str, poppler_path: Optional[str] = None) -> str:
    """تبدیل PDF به متن OCR با دقت بالا و سرعت بیشتر"""
    try:
        # کاهش DPI از 300 به 200 برای افزایش سرعت
        images = convert_from_path(pdf_path, dpi=200, poppler_path=poppler_path)
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
# 📥 دریافت فایل از تلگرام
# ----------------------------
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

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
        await message.reply_text("⏳ در حال استخراج متن با سرعت بالا...")

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

        for i in range(0, len(text), 4000):
            await message.reply_text(text[i:i + 4000])

        await message.reply_text("✅ متن با موفقیت استخراج شد (نسخه سریع).")
    except Exception as e:
        logger.exception(e)
        await message.reply_text(f"❌ خطا در پردازش فایل: {str(e)}")
    finally:
        for f in Path(tmp_dir).glob("*"):
            f.unlink(missing_ok=True)
        Path(tmp_dir).rmdir()


# ----------------------------
# 🚀 دستور شروع
# ----------------------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 سلام!\nمن ربات OCR سریع هستم.\n"
        "فایل PDF یا عکس بفرست تا در چند ثانیه متنش رو برات استخراج کنم 🚀"
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

    logger.info("🤖 OCR Bot (Fast Edition) started successfully ...")
    app.run_polling()


if __name__ == "__main__":
    main()
