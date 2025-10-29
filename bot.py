import os
import tempfile
import logging
from pathlib import Path
from typing import Optional
import re
import urllib.request

import pytesseract
from PIL import Image, ImageFilter, ImageEnhance, ImageOps
from pdf2image import convert_from_path
import fitz  # PyMuPDF
from concurrent.futures import ThreadPoolExecutor

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# -----------------------
# تنظیمات و لاگ
# -----------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
POPPLER_PATH = os.environ.get("POPPLER_PATH", "/usr/bin")

# تعداد نخ‌ها برای پردازش صفحات PDF (برای سرعت)
MAX_WORKERS = int(os.environ.get("OCR_MAX_WORKERS", "4"))
executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

# تنظیمات Tesseract برای دقت بهتر فارسی
OCR_CONFIG = "--oem 3 --psm 6 -c preserve_interword_spaces=1"

# -----------------------
# توابع کمکی برای بهبود تصویر (برای دقت OCR)
# -----------------------
def preprocess_pil_image(img: Image.Image) -> Image.Image:
    """پیش‌پردازش تصویر برای بهبود دقت OCR"""
    try:
        # تبدیل به خاکستری
        img = img.convert("L")

        # افزایش اندازه اگر خیلی کوچک باشه (افزایش دقت)
        target_w = 1600
        if img.width < target_w:
            ratio = target_w / float(img.width)
            new_h = int(img.height * ratio)
            img = img.resize((target_w, new_h), Image.Resampling.BICUBIC)

        # کاهش نویز و افزایش کنتراست و تیزی
        img = img.filter(ImageFilter.MedianFilter(size=3))
        img = ImageOps.autocontrast(img, cutoff=1)
        enhancer = ImageEnhance.Sharpness(img)
        img = enhancer.enhance(1.5)

        # آستانه (اختیاری — کمک می‌کند حروف واضح‌تر شوند)
        # مقدار آستانه را روی 127 قرار می‌دهیم؛ اگر نیاز بود می‌توان آن را تغییر داد.
        img = img.point(lambda p: 255 if p > 127 else 0)

        return img
    except Exception as e:
        logger.exception(f"preprocess error: {e}")
        return img


def detect_language_from_image(image: Image.Image) -> str:
    """تشخیص زبان غالب تصویر (فارسی/انگلیسی/ترکیبی)"""
    try:
        # نمونه‌برداری سریع با اندازه کوچک و psm سریع
        sample = image.copy()
        sample.thumbnail((800, 800))
        text_sample = pytesseract.image_to_string(sample, lang="fas+eng", config="--psm 6")
        persian_chars = len(re.findall(r"[\u0600-\u06FF]", text_sample))
        english_chars = len(re.findall(r"[A-Za-z]", text_sample))
        if persian_chars > english_chars * 1.5:
            return "fas"
        elif english_chars > persian_chars * 1.5:
            return "eng"
        else:
            return "fas+eng"
    except Exception as e:
        logger.error(f"language detect error: {e}")
        return "fas+eng"


# -----------------------
# استخراج متن
# -----------------------
def extract_text_from_pdf_digital(pdf_path: str) -> str:
    """استخراج متن digital (selectable) از PDF با PyMuPDF"""
    texts = []
    try:
        with fitz.open(pdf_path) as doc:
            for page in doc:
                txt = page.get_text("text")
                if txt:
                    texts.append(txt)
    except Exception as e:
        logger.exception(f"PDF digital extraction error: {e}")
    return "\n\n".join(texts).strip()


def ocr_image_with_lang(img: Image.Image, lang: str) -> str:
    """اجرای OCR روی تصویر (پیش‌پردازش + pytesseract)"""
    try:
        pre = preprocess_pil_image(img)
        return pytesseract.image_to_string(pre, lang=lang, config=OCR_CONFIG).strip()
    except Exception as e:
        logger.exception(f"OCR image error: {e}")
        return ""


def ocr_pdf_to_text(pdf_path: str, poppler_path: Optional[str] = None) -> str:
    """تبدیل PDF به تصاویر و اجرای OCR (چندنخی برای سرعت)"""
    try:
        images = convert_from_path(pdf_path, dpi=300, poppler_path=poppler_path)
    except Exception as e:
        logger.exception(f"pdf->image error: {e}")
        return ""

    # تابع پردازش یک صفحه
    def process_page(img):
        try:
            lang = detect_language_from_image(img)
            return ocr_image_with_lang(img, lang)
        except Exception as e:
            logger.exception(f"page process error: {e}")
            return ""

    # پردازش چندنخی صفحات (حفظ ترتیب)
    futures = [executor.submit(process_page, img.copy()) for img in images]
    results = [f.result() for f in futures]
    texts = [r for r in results if r]
    return "\n\n".join(texts).strip()


# -----------------------
# حذف webhook قبلی (کاهش احتمال conflict)
# -----------------------
def ensure_delete_webhook(token: str):
    try:
        url = f"https://api.telegram.org/bot{token}/deleteWebhook"
        urllib.request.urlopen(url, timeout=10)
        logger.info("deleteWebhook called (if any webhook existed).")
    except Exception:
        # بی‌خیال می‌شویم اگر خطا بده — فقط تلاش کردیم
        pass


# -----------------------
# هندل پیام‌ها
# -----------------------
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    # تشخیص فایل یا عکس
    if message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name or "file.pdf"
    elif message.photo:
        photo = message.photo[-1]
        file_id = photo.file_id
        file_name = f"{photo.file_unique_id}.jpg"
    else:
        await message.reply_text("📄 لطفاً یک فایل PDF یا تصویر ارسال کنید.")
        return

    tmp_dir = tempfile.mkdtemp()
    local_path = os.path.join(tmp_dir, file_name)

    try:
        # دانلود فایل از تلگرام
        tg_file = await context.bot.get_file(file_id)
        await tg_file.download_to_drive(custom_path=local_path)

        # استخراج متن: در ابتدا تلاش برای متن دیجیتال PDF
        text = ""
        if file_name.lower().endswith(".pdf"):
            await message.reply_text("📑 در حال استخراج متن از PDF ...")
            text = extract_text_from_pdf_digital(local_path)
            if not text.strip():
                await message.reply_text("🔍 متن دیجیتال یافت نشد؛ اجرای OCR (چندصفحه‌ای) ...")
                text = ocr_pdf_to_text(local_path, poppler_path=POPPLER_PATH)
        else:
            await message.reply_text("🖼️ در حال پردازش تصویر و اجرای OCR ...")
            img = Image.open(local_path)
            lang = detect_language_from_image(img)
            text = ocr_image_with_lang(img, lang)

        if not text.strip():
            await message.reply_text("⚠️ هیچ متنی قابل استخراج نبود.")
            return

        # ارسال متن کامل داخل چت (تقسیم به قطعات امن برای تلگرام)
        max_len = 3900
        # حذف فضاهای اضافی و کاراکترهای نامرغوب در ابتدا/انتها
        text = text.strip()
        for i in range(0, len(text), max_len):
            await message.reply_text(text[i:i + max_len])

        await message.reply_text("✅ استخراج متن با موفقیت انجام شد.")
    except Exception as e:
        logger.exception(f"Error processing file: {e}")
        await message.reply_text(f"❌ خطا در پردازش فایل: {str(e)}")
    finally:
        # پاکسازی موقت
        try:
            for f in Path(tmp_dir).glob("*"):
                f.unlink(missing_ok=True)
            Path(tmp_dir).rmdir()
        except Exception:
            pass


# -----------------------
# فرمان استارت
# -----------------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 سلام!\n"
        "من ربات استخراج متن هوشمند هستم.\n\n"
        "📄 یک PDF یا تصویر بفرست تا متن (فارسی/انگلیسی) رو مستقیم داخل چت برات ارسال کنم."
    )


# -----------------------
# اجرا (main)
# -----------------------
def main():
    if not BOT_TOKEN:
        raise RuntimeError("❌ BOT_TOKEN is missing!")

    # تلاش برای حذف هر webhook قبلی (کاهش خطر conflict)
    ensure_delete_webhook(BOT_TOKEN)

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file))

    logger.info("🤖 Bot started and waiting for files...")
    app.run_polling()


if __name__ == "__main__":
    main()
