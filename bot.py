import os
import tempfile
import logging
import re
import asyncio
from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

import pytesseract
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
from pdf2image import convert_from_path
import fitz  # PyMuPDF
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# -------------------------------------------
# ⚙️ تنظیمات اولیه
# -------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
POPPLER_PATH = os.environ.get("POPPLER_PATH", "/usr/bin")

# تعداد نخ‌ها برای OCR چندصفحه‌ای
MAX_WORKERS = int(os.environ.get("OCR_MAX_WORKERS", "4"))
executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

# پیکربندی OCR برای دقت بالا در فارسی
OCR_CONFIG = (
    "--oem 3 --psm 6 "
    "-c preserve_interword_spaces=1 "
    "-c tessedit_char_blacklist=~`@#$%^*_+=[]{}<> "
)

# -------------------------------------------
# 🧩 پیش‌پردازش تصویر مخصوص PDFهای رسمی
# -------------------------------------------
def preprocess_image_for_ocr(img: Image.Image) -> Image.Image:
    """
    پیش‌پردازش تصویری بهینه برای متن‌های رسمی فارسی:
    - حذف نویز خاکستری
    - افزایش شارپنس و وضوح
    - adaptive threshold برای وضوح حروف
    """
    try:
        # 1️⃣ تبدیل به خاکستری
        img = img.convert("L")

        # 2️⃣ بزرگ کردن اگر وضوح پایین باشد
        if img.width < 1200:
            scale = 1200 / img.width
            img = img.resize((int(img.width * scale), int(img.height * scale)), Image.Resampling.LANCZOS)

        # 3️⃣ افزایش وضوح و کنتراست
        img = ImageOps.autocontrast(img, cutoff=2)
        img = ImageEnhance.Sharpness(img).enhance(2.0)
        img = ImageEnhance.Contrast(img).enhance(1.5)

        # 4️⃣ Threshold برای حذف واترمارک
        img = img.point(lambda x: 255 if x > 150 else 0, mode="1")

        return img
    except Exception as e:
        logger.error(f"Preprocess error: {e}")
        return img


# -------------------------------------------
# 🌐 تشخیص زبان تصویر
# -------------------------------------------
def detect_language_from_image(image: Image.Image) -> str:
    """
    تشخیص خودکار بین فارسی و انگلیسی
    """
    try:
        txt = pytesseract.image_to_string(image, lang="fas+eng", config="--psm 6")
        farsi = len(re.findall(r'[\u0600-\u06FF]', txt))
        english = len(re.findall(r'[A-Za-z]', txt))
        if farsi >= english:
            return "fas"
        return "eng"
    except Exception:
        return "fas+eng"


# -------------------------------------------
# 🧠 OCR از تصویر با بازسازی فاصله‌ها و راست‌به‌چپ
# -------------------------------------------
def ocr_image_precise(img: Image.Image, lang: str) -> str:
    """
    اجرای OCR دقیق و بازسازی ساختار راست‌به‌چپ فارسی
    """
    try:
        processed = preprocess_image_for_ocr(img)

        # OCR با تحلیل Bounding Box برای بازسازی فضاها
        data = pytesseract.image_to_data(processed, lang=lang, config=OCR_CONFIG, output_type=pytesseract.Output.DICT)

        # بازسازی بر اساس مختصات سطرها
        lines = {}
        for i, txt in enumerate(data["text"]):
            if not txt.strip():
                continue
            y = data["top"][i]
            line_y = round(y / 30)  # گروه‌بندی تقریبی خطوط
            lines.setdefault(line_y, []).append((data["left"][i], txt))

        # بازسازی خطوط راست‌به‌چپ
        sorted_lines = []
        for _, items in sorted(lines.items()):
            items = sorted(items, key=lambda x: x[0], reverse=True)
            line_text = " ".join(word for _, word in items)
            sorted_lines.append(line_text)

        text = "\n".join(sorted_lines).strip()

        # اصلاح کاراکترها و فاصله‌ها
        text = re.sub(r"\s{2,}", " ", text)
        text = text.replace("ي", "ی").replace("ك", "ک")

        # اصلاح اعداد فارسی/انگلیسی
        trans_table = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
        text = text.translate(trans_table)

        return text
    except Exception as e:
        logger.error(f"OCR precise error: {e}")
        return ""


# -------------------------------------------
# 📄 OCR از PDF با دقت بالا
# -------------------------------------------
def ocr_pdf_to_text(pdf_path: str, poppler_path: Optional[str] = None) -> str:
    """
    OCR مخصوص PDF رسمی — ترکیب چند صفحه با بازسازی کامل
    """
    try:
        images = convert_from_path(pdf_path, dpi=300, poppler_path=poppler_path)
    except Exception as e:
        logger.error(f"PDF to image error: {e}")
        return ""

    def process_page(img):
        lang = detect_language_from_image(img)
        return ocr_image_precise(img, lang)

    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(images))) as pool:
        results = pool.map(process_page, images)
    return "\n\n".join(results).strip()


# -------------------------------------------
# 📨 هندل پیام‌های تلگرام
# -------------------------------------------
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
        await message.reply_text("⏳ در حال پردازش متن با دقت بالا، لطفاً صبر کنید...")

        def process():
            if file_name.lower().endswith(".pdf"):
                text = ocr_pdf_to_text(local_path, poppler_path=POPPLER_PATH)
            else:
                img = Image.open(local_path)
                lang = detect_language_from_image(img)
                text = ocr_image_precise(img, lang)
            return text

        loop = asyncio.get_running_loop()
        text = await loop.run_in_executor(executor, process)

        if not text.strip():
            await message.reply_text("⚠️ هیچ متنی قابل استخراج نبود.")
            return

        # ارسال در چند پیام برای جلوگیری از محدودیت تلگرام
        max_len = 4000
        for i in range(0, len(text), max_len):
            await message.reply_text(text[i:i + max_len])

        await message.reply_text("✅ استخراج متن با موفقیت انجام شد.")
    except Exception as e:
        logger.exception(e)
        await message.reply_text(f"❌ خطا در پردازش فایل: {str(e)}")
    finally:
        try:
            for f in Path(tmp_dir).glob("*"):
                f.unlink(missing_ok=True)
            Path(tmp_dir).rmdir()
        except Exception:
            pass


# -------------------------------------------
# 🚀 دستور /start
# -------------------------------------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 سلام!\n"
        "من ربات OCR فارسی حرفه‌ای هستم 📄\n"
        "کافیه فایل PDF یا عکس اسکن‌شده بفرستی تا با دقت بالا متن فارسی، انگلیسی یا عربی رو برات استخراج کنم."
    )


# -------------------------------------------
# 🚀 اجرای اصلی
# -------------------------------------------
def main():
    if not BOT_TOKEN:
        raise RuntimeError("❌ BOT_TOKEN تنظیم نشده!")

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file))

    logger.info("🤖 OCR Bot started successfully ...")
    app.run_polling()


if __name__ == "__main__":
    main()
