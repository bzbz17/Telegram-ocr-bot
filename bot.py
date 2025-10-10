# =====================================================
# 📄 bot.py — نسخه نهایی با دقت بالا برای فارسی، عربی و انگلیسی
# شامل بهینه‌سازی OCR برای فونت‌های فارسی، نستعلیق و خطوط اسکن‌شده
# و کنترل هوشمند سرعت OCR چندنخی
# =====================================================

import os
import tempfile
import logging
import re
import asyncio
import math
from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

import pytesseract
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
from pdf2image import convert_from_path
import fitz  # PyMuPDF
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# -----------------------
# تنظیمات لاگینگ
# -----------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
POPPLER_PATH = os.environ.get("POPPLER_PATH", "/usr/bin")

# تعداد نخ‌ها برای OCR چندصفحه‌ای
MAX_WORKERS = int(os.environ.get("OCR_MAX_WORKERS", "4"))
executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

# پیکربندی پایه OCR
OCR_CONFIG = "--oem 3 --psm 6 -c preserve_interword_spaces=1"


# -----------------------
# 🎨 پیش‌پردازش هوشمند تصویر
# -----------------------
def preprocess_pil_image(img: Image.Image) -> Image.Image:
    """
    پردازش هوشمند تصویر:
    - تنظیم روشنایی و کنتراست بر اساس نوع فونت
    - تشخیص تراکم خطوط برای فونت نستعلیق یا نازک
    - استفاده از فیلترهای نویز متفاوت بسته به نوع تصویر
    """
    try:
        img = img.convert("L")
        w, h = img.size
        ratio = h / w

        # 🔹 اگر تصویر خیلی کوچک بود، بزرگش کن برای دقت بیشتر OCR
        if w < 1400:
            scale = 1400 / w
            img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.BICUBIC)

        # 🔹 بررسی تراکم پیکسل‌ها برای تشخیص نوع فونت
        pixels = list(img.getdata())
        darkness = sum(1 for p in pixels if p < 120) / len(pixels)

        if darkness > 0.45:
            # فونت ضخیم یا تصویر اسکن‌شده با نویز زیاد
            img = img.filter(ImageFilter.MedianFilter(size=3))
            img = ImageOps.autocontrast(img, cutoff=1)
            img = ImageEnhance.Contrast(img).enhance(1.4)
        else:
            # فونت نازک (مثلاً نستعلیق یا تایپ‌شده)
            img = img.filter(ImageFilter.SMOOTH_MORE)
            img = ImageEnhance.Sharpness(img).enhance(1.8)
            img = ImageEnhance.Brightness(img).enhance(1.2)

        img = img.point(lambda x: 0 if x < 130 else 255, '1')
        return img
    except Exception as e:
        logger.error(f"preprocess error: {e}")
        return img


# -----------------------
# 🌐 تشخیص زبان تصویر
# -----------------------
def detect_language_from_image(image: Image.Image) -> str:
    """
    تشخیص زبان غالب (فارسی، عربی، انگلیسی)
    """
    try:
        sample = image.copy()
        sample.thumbnail((900, 900))
        txt = pytesseract.image_to_string(sample, lang="fas+ara+eng", config="--psm 6")
        farsi = len(re.findall(r'[\u0600-\u06FF]', txt))
        arabic = len(re.findall(r'[\u0750-\u077F]', txt))
        english = len(re.findall(r'[A-Za-z]', txt))

        if farsi > english * 1.5 and farsi >= arabic:
            return "fas"
        if arabic > english * 1.5 and arabic > farsi:
            return "ara"
        if english > farsi * 1.5 and english > arabic:
            return "eng"
        return "fas+eng+ara"
    except Exception as e:
        logger.error(f"Language detection failed: {e}")
        return "fas+eng+ara"


# -----------------------
# 📘 استخراج متن دیجیتال از PDF
# -----------------------
def extract_text_from_pdf_digital(pdf_path: str) -> str:
    """
    اگر PDF دیجیتال باشد، از متن داخلی استفاده می‌کند.
    """
    try:
        with fitz.open(pdf_path) as doc:
            pages = [page.get_text("text") for page in doc]
        return "\n".join(pages).strip()
    except Exception as e:
        logger.error(f"PDF text extraction error: {e}")
        return ""


# -----------------------
# 🧠 OCR برای تصویر
# -----------------------
def ocr_image_to_text(img: Image.Image, lang: str) -> str:
    """
    اجرای OCR روی یک تصویر با تنظیمات دقیق
    """
    try:
        processed = preprocess_pil_image(img)
        return pytesseract.image_to_string(processed, lang=lang, config=OCR_CONFIG).strip()
    except Exception as e:
        logger.error(f"OCR image error: {e}")
        return ""


# -----------------------
# 📄 OCR برای PDF چند صفحه‌ای
# -----------------------
def ocr_pdf_to_text(pdf_path: str, poppler_path: Optional[str] = None) -> str:
    """
    OCR چندنخی PDF با کنترل هوشمند سرعت و دما (برای Render)
    """
    try:
        images = convert_from_path(pdf_path, dpi=300, poppler_path=poppler_path)
    except Exception as e:
        logger.error(f"PDF to image conversion error: {e}")
        return ""

    # اگر صفحات زیاد باشد، OCR را دسته‌ای انجام می‌دهیم تا CPU زیاد درگیر نشود
    batch_size = max(1, math.ceil(len(images) / MAX_WORKERS))
    results = []

    def process_batch(batch):
        texts = []
        for img in batch:
            lang = detect_language_from_image(img)
            txt = ocr_image_to_text(img, lang)
            if txt.strip():
                texts.append(txt)
        return "\n\n".join(texts)

    batches = [images[i:i + batch_size] for i in range(0, len(images), batch_size)]
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(batches))) as pool:
        for r in pool.map(process_batch, batches):
            results.append(r)

    return "\n\n".join(results).strip()


# -----------------------
# 📨 هندل فایل‌ها (PDF / Image)
# -----------------------
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
        await message.reply_text("📄 لطفاً یک فایل PDF یا تصویر ارسال کنید.")
        return

    tmp_dir = tempfile.mkdtemp()
    local_path = os.path.join(tmp_dir, file_name)

    try:
        telegram_file = await context.bot.get_file(file_id)
        await telegram_file.download_to_drive(custom_path=local_path)

        await message.reply_text("⏳ در حال پردازش فایل و استخراج متن با دقت بالا...")

        def process_file():
            if file_name.lower().endswith(".pdf"):
                text = extract_text_from_pdf_digital(local_path)
                if not text:
                    text = ocr_pdf_to_text(local_path, poppler_path=POPPLER_PATH)
            else:
                img = Image.open(local_path)
                lang = detect_language_from_image(img)
                text = ocr_image_to_text(img, lang)
            return text

        loop = asyncio.get_running_loop()
        text = await loop.run_in_executor(executor, process_file)

        if not text.strip():
            await message.reply_text("⚠️ هیچ متنی قابل استخراج نبود.")
            return

        # ارسال متن به صورت قطعه‌قطعه تا محدودیت تلگرام رعایت شود
        max_len = 4000
        for i in range(0, len(text), max_len):
            await message.reply_text(text[i:i + max_len])

        await message.reply_text("✅ استخراج متن با موفقیت انجام شد.")
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


# -----------------------
# 🚀 فرمان /start
# -----------------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 سلام!\n"
        "من ربات استخراج متن هوشمند هستم 📄\n"
        "کافیه فایل PDF یا عکس بفرستی تا با دقت بالا متن فارسی، عربی یا انگلیسی رو برات استخراج کنم."
    )


# -----------------------
# 🚀 اجرای اصلی
# -----------------------
def main():
    if not BOT_TOKEN:
        raise RuntimeError("❌ متغیر BOT_TOKEN تنظیم نشده!")

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file))

    logger.info("🤖 Bot started successfully and is waiting for files...")
    app.run_polling()


if __name__ == "__main__":
    main()
