import os
import logging
import tempfile
import re
import pytesseract
import fitz  # PyMuPDF
from PIL import Image
from pdf2image import convert_from_path
from arabic_reshaper import reshape
from bidi.algorithm import get_display
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# ------------------------------
# تنظیمات لاگ
# ------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ------------------------------
# تنظیم متغیرهای محیطی
# ------------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN")
POPPLER_PATH = os.environ.get("POPPLER_PATH", "/usr/bin")

# ------------------------------
# تابع اصلاح جهت متن‌های فارسی و عربی
# ------------------------------
def fix_rtl_text(text: str) -> str:
    """اصلاح جهت و نمایش صحیح حروف فارسی/عربی"""
    try:
        lines = text.splitlines()
        fixed_lines = []
        for line in lines:
            if re.search(r'[\u0600-\u06FF]', line):  # اگر متن فارسی/عربی دارد
                reshaped = reshape(line)
                fixed_lines.append(get_display(reshaped))
            else:
                fixed_lines.append(line)
        return "\n".join(fixed_lines)
    except Exception as e:
        logger.error(f"RTL Fix Error: {e}")
        return text

# ------------------------------
# تابع تشخیص زبان از تصویر
# ------------------------------
def detect_language(image: Image.Image) -> str:
    """تشخیص زبان غالب تصویر"""
    text_preview = pytesseract.image_to_string(image, lang="fas+ara+eng", config="--psm 6")
    persian = len(re.findall(r'[\u0600-\u06FF]', text_preview))
    english = len(re.findall(r'[A-Za-z]', text_preview))
    if persian > english * 1.5:
        return "fas"
    elif english > persian * 1.5:
        return "eng"
    else:
        return "fas+ara+eng"

# ------------------------------
# OCR تصویر
# ------------------------------
def extract_text_tesseract(image: Image.Image, lang="fas+ara+eng") -> str:
    """استخراج متن از تصویر با دقت بالا"""
    config = "--oem 1 --psm 6"
    text = pytesseract.image_to_string(image, lang=lang, config=config)
    text = text.replace("ﻻ", "لا").replace("ﺎ", "ا")
    return text.strip()

# ------------------------------
# استخراج متن از PDF دیجیتال
# ------------------------------
def extract_text_from_pdf_digital(pdf_path: str) -> str:
    """اگر PDF دیجیتال باشد، متن مستقیم استخراج می‌شود"""
    text_blocks = []
    try:
        with fitz.open(pdf_path) as doc:
            for page in doc:
                content = page.get_text("text")
                if content.strip():
                    text_blocks.append(content)
    except Exception as e:
        logger.error(f"PDF digital extract error: {e}")
    return "\n".join(text_blocks).strip()

# ------------------------------
# استخراج متن از PDF اسکن‌شده با OCR
# ------------------------------
def extract_text_from_pdf_ocr(pdf_path: str) -> str:
    """OCR روی صفحات PDF اسکن‌شده"""
    try:
        images = convert_from_path(pdf_path, dpi=250, poppler_path=POPPLER_PATH)
        all_text = []
        for img in images:
            lang = detect_language(img)
            text = extract_text_tesseract(img, lang)
            all_text.append(text)
        return "\n\n".join(all_text).strip()
    except Exception as e:
        logger.error(f"OCR PDF Error: {e}")
        return ""

# ------------------------------
# هندل فایل ارسال‌شده به ربات
# ------------------------------
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    if message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name
    elif message.photo:
        photo = message.photo[-1]
        file_id = photo.file_id
        file_name = f"{photo.file_unique_id}.jpg"
    else:
        await message.reply_text("📄 لطفاً یک فایل PDF یا عکس ارسال کنید.")
        return

    tmp_dir = tempfile.mkdtemp()
    local_path = os.path.join(tmp_dir, file_name)

    try:
        telegram_file = await context.bot.get_file(file_id)
        await telegram_file.download_to_drive(custom_path=local_path)
        await message.reply_text("⏳ در حال پردازش و استخراج متن ...")

        # استخراج متن بر اساس نوع فایل
        if file_name.lower().endswith(".pdf"):
            text = extract_text_from_pdf_digital(local_path)
            if not text:
                text = extract_text_from_pdf_ocr(local_path)
        else:
            img = Image.open(local_path)
            lang = detect_language(img)
            text = extract_text_tesseract(img, lang)

        if not text.strip():
            await message.reply_text("⚠️ متنی شناسایی نشد.")
            return

        text = fix_rtl_text(text)
        await message.reply_text(f"📝 متن استخراج‌شده:\n\n{text}")

    except Exception as e:
        logger.error(f"Processing error: {e}")
        await message.reply_text(f"❌ خطا در پردازش فایل: {str(e)}")
    finally:
        try:
            for f in os.listdir(tmp_dir):
                os.remove(os.path.join(tmp_dir, f))
            os.rmdir(tmp_dir)
        except Exception:
            pass

# ------------------------------
# فرمان شروع ربات
# ------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 سلام!\n"
        "من ربات OCR هوشمند هستم.\n"
        "📄 فایل PDF یا عکس بفرست تا متن فارسی، عربی یا انگلیسی‌شو استخراج کنم."
    )

# ------------------------------
# شروع برنامه
# ------------------------------
def main():
    if not BOT_TOKEN:
        raise RuntimeError("❌ BOT_TOKEN در محیط تنظیم نشده!")

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file))

    logger.info("🤖 Bot started successfully.")
    app.run_polling()

if __name__ == "__main__":
    main()
