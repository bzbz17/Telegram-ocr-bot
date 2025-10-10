import os
import tempfile
import logging
import re
from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

import pytesseract
from PIL import Image, ImageEnhance, ImageFilter
from pdf2image import convert_from_path
import fitz  # PyMuPDF
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters


# ──────────────────────────────────────────────
# 📜 پیکربندی اولیه و تنظیمات کلی
# ──────────────────────────────────────────────

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
POPPLER_PATH = os.environ.get("POPPLER_PATH", "/usr/bin")

# برای اجرای سریع‌تر OCR به‌صورت موازی
executor = ThreadPoolExecutor(max_workers=4)


# ──────────────────────────────────────────────
# 🧩 توابع بهینه‌سازی تصویر قبل از OCR
# ──────────────────────────────────────────────

def preprocess_image(img: Image.Image) -> Image.Image:
    """
    🔹 قبل از OCR، تصویر را بهینه می‌کند تا تشخیص متن دقیق‌تر انجام شود.
    - افزایش وضوح و کنتراست
    - تبدیل به سیاه‌وسفید
    - حذف نویز
    """
    try:
        img = img.convert("L")  # به خاکستری
        img = img.filter(ImageFilter.MedianFilter())  # حذف نویز
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(2)  # افزایش کنتراست
        return img
    except Exception as e:
        logger.error(f"Image preprocessing error: {e}")
        return img


# ──────────────────────────────────────────────
# 🌍 تشخیص زبان به صورت خودکار از تصویر
# ──────────────────────────────────────────────

def detect_language_from_image(image: Image.Image) -> str:
    """
    🔹 تشخیص خودکار زبان غالب (فارسی، انگلیسی، عربی)
    بر اساس شمارش کاراکترهای خاص هر زبان
    """
    try:
        text_sample = pytesseract.image_to_string(image, lang="fas+eng+ara", config="--psm 6")
        persian_chars = len(re.findall(r'[\u0600-\u06FF]', text_sample))
        english_chars = len(re.findall(r'[A-Za-z]', text_sample))
        arabic_chars = len(re.findall(r'[\u0750-\u077F]', text_sample))

        # زبان غالب را بر اساس بیشترین کاراکتر تشخیص می‌دهیم
        if persian_chars > english_chars and persian_chars > arabic_chars:
            return "fas"
        elif arabic_chars > persian_chars and arabic_chars > english_chars:
            return "ara"
        elif english_chars > persian_chars and english_chars > arabic_chars:
            return "eng"
        else:
            return "fas+eng+ara"
    except Exception:
        return "fas+eng+ara"


# ──────────────────────────────────────────────
# 📄 استخراج متن دیجیتال از PDF
# ──────────────────────────────────────────────

def extract_text_from_pdf_digital(pdf_path: str) -> str:
    """
    🔹 اگر PDF متنی باشد (نه اسکن)، مستقیماً متن را استخراج می‌کند.
    """
    try:
        text = []
        with fitz.open(pdf_path) as doc:
            for page in doc:
                text.append(page.get_text("text"))
        return "\n".join(text).strip()
    except Exception as e:
        logger.error(f"PDF extraction error: {e}")
        return ""


# ──────────────────────────────────────────────
# 🧠 OCR روی PDF اسکن‌شده
# ──────────────────────────────────────────────

def ocr_pdf_to_text(pdf_path: str, poppler_path: Optional[str] = None) -> str:
    """
    🔹 تبدیل هر صفحه PDF اسکن‌شده به تصویر و اجرای OCR
    - پشتیبانی از فارسی، انگلیسی و عربی
    - حفظ فاصله‌ها و ترتیب متن
    """
    try:
        images = convert_from_path(pdf_path, dpi=300, poppler_path=poppler_path)
    except Exception as e:
        logger.error(f"PDF to image error: {e}")
        return ""

    results = []
    for img in images:
        img = preprocess_image(img)  # بهینه‌سازی تصویر
        lang = detect_language_from_image(img)
        text = pytesseract.image_to_string(
            img,
            lang=lang,
            config="--psm 6 --oem 3 -c preserve_interword_spaces=1"
        )
        results.append(text)
    return "\n\n".join(results).strip()


# ──────────────────────────────────────────────
# 🖼️ OCR از تصویر
# ──────────────────────────────────────────────

def ocr_image_to_text(image_path: str) -> str:
    """
    🔹 اجرای OCR روی تصویر تکی (JPG / PNG)
    """
    try:
        img = Image.open(image_path)
        img = preprocess_image(img)
        lang = detect_language_from_image(img)
        text = pytesseract.image_to_string(
            img,
            lang=lang,
            config="--psm 6 --oem 3 -c preserve_interword_spaces=1"
        )
        return text.strip()
    except Exception as e:
        logger.error(f"OCR image error: {e}")
        return ""


# ──────────────────────────────────────────────
# 💬 هندل پیام‌ها (دریافت فایل PDF یا تصویر)
# ──────────────────────────────────────────────

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    # دریافت فایل از پیام
    file_id = None
    file_name = None
    if message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name
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
        telegram_file = await context.bot.get_file(file_id)
        await telegram_file.download_to_drive(custom_path=local_path)

        await message.reply_text("⏳ در حال تجزیه و تحلیل و استخراج متن با دقت بالا ...")

        def process():
            if file_name.lower().endswith(".pdf"):
                text = extract_text_from_pdf_digital(local_path)
                if not text.strip():
                    text = ocr_pdf_to_text(local_path, poppler_path=POPPLER_PATH)
            else:
                text = ocr_image_to_text(local_path)
            return text

        # اجرای پردازش در ThreadPool
        text = await context.application.run_in_executor(executor, process)

        if not text.strip():
            await message.reply_text("⚠️ هیچ متنی قابل استخراج نبود.")
            return

        # تقسیم متن در صورت طولانی بودن
        max_len = 4000
        chunks = [text[i:i + max_len] for i in range(0, len(text), max_len)]
        for part in chunks:
            await message.reply_text(part)

    except Exception as e:
        logger.exception(e)
        await message.reply_text(f"❌ خطا در پردازش فایل: {e}")

    finally:
        for f in Path(tmp_dir).glob("*"):
            f.unlink(missing_ok=True)
        Path(tmp_dir).rmdir()


# ──────────────────────────────────────────────
# 🚀 دستور /start برای شروع گفتگو
# ──────────────────────────────────────────────

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 سلام!\n"
        "من ربات استخراج متن هوشمند هستم 🤖\n\n"
        "📸 عکس یا فایل PDF بفرست تا متن فارسی، انگلیسی یا عربی‌شو با دقت بالا استخراج کنم."
    )


# ──────────────────────────────────────────────
# 🧩 اجرای اصلی برنامه
# ──────────────────────────────────────────────

def main():
    if not BOT_TOKEN:
        raise RuntimeError("❌ BOT_TOKEN تعریف نشده!")

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file))

    logger.info("🤖 OCR Bot is now running ...")
    app.run_polling()


if __name__ == "__main__":
    main()
