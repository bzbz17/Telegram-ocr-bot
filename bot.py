import os
import re
import cv2
import tempfile
import logging
import threading
from flask import Flask
from PIL import Image, ImageEnhance, ImageFilter
from pdf2image import convert_from_path
import pytesseract
import fitz  # PyMuPDF
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# =================== تنظیمات پایه ===================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
POPPLER_PATH = os.environ.get("POPPLER_PATH", "/usr/bin")

# =================== Flask برای UptimeRobot ===================
app = Flask(__name__)

@app.route("/")
def home():
    return "✅ OCR bot is alive and running!"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

# =================== بهبود تصویر (خودکار) ===================
def auto_preprocess_image(image_path: str):
    """اگر تصویر تار یا کم‌نور بود خودش اصلاحش می‌کنه"""
    img = Image.open(image_path).convert("L")

    # بررسی تار بودن تصویر
    np_img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    laplacian_var = cv2.Laplacian(np_img, cv2.CV_64F).var()
    if laplacian_var < 80:
        logger.info("🌀 تصویر تار تشخیص داده شد → Sharpening applied.")
        img = img.filter(ImageFilter.SHARPEN)

    # بررسی روشنایی
    brightness = ImageEnhance.Brightness(img)
    img = brightness.enhance(1.2)

    # حذف نویز
    img = img.filter(ImageFilter.MedianFilter(size=3))

    temp_file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    img.save(temp_file.name)
    return temp_file.name

# =================== تشخیص زبان ترکیبی ===================
def detect_language(text_sample: str):
    """بر اساس حروف، ترکیب زبان رو مشخص می‌کنه"""
    fa = len(re.findall(r'[\u0600-\u06FF]', text_sample))
    en = len(re.findall(r'[A-Za-z]', text_sample))
    if fa > en:
        return "fas+ara"
    return "eng"

# =================== پردازش جدول‌ها ===================
def split_table_text(text: str):
    """اگر متن شامل جدول یا ساختار ستونی باشه، هر بخش جدا برگردونده میشه"""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    blocks, block = [], []
    for line in lines:
        if re.match(r'[-–=]+', line):  # تشخیص خط جداکننده جدول
            if block:
                blocks.append("\n".join(block))
                block = []
        else:
            block.append(line)
    if block:
        blocks.append("\n".join(block))
    return blocks

# =================== OCR از تصویر ===================
def extract_text_from_image(image_path: str):
    clean_path = auto_preprocess_image(image_path)
    lang = "fas+ara+eng"
    text = pytesseract.image_to_string(Image.open(clean_path), lang=lang, config="--psm 6")
    return text.strip()

# =================== OCR از PDF ===================
def extract_text_from_pdf(pdf_path: str):
    text_result = []
    try:
        with fitz.open(pdf_path) as doc:
            for page in doc:
                txt = page.get_text("text")
                if txt.strip():
                    text_result.append(txt)

        # اگر متن دیجیتال نداشت، OCR کن
        if not "".join(text_result).strip():
            images = convert_from_path(pdf_path, dpi=250, poppler_path=POPPLER_PATH)
            for img in images:
                temp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                img.save(temp.name, "PNG")
                text = extract_text_from_image(temp.name)
                text_result.append(text)

    except Exception as e:
        logger.error(f"PDF OCR error: {e}")

    return "\n".join(text_result).strip()

# =================== هندلرها ===================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 سلام! من ربات هوشمند OCR هستم.\n\n"
        "📄 فایل PDF یا عکس بفرست تا متنش (فارسی، عربی، انگلیسی) با حفظ راست‌به‌چپ و ساختار جدول استخراج بشه ✅"
    )

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    file_name = None
    file_id = None

    if message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name
    elif message.photo:
        file_id = message.photo[-1].file_id
        file_name = f"{file_id}.jpg"
    else:
        await message.reply_text("📎 لطفاً فایل PDF یا عکس بفرست.")
        return

    tmp_dir = tempfile.mkdtemp()
    local_path = os.path.join(tmp_dir, file_name)
    telegram_file = await context.bot.get_file(file_id)
    await telegram_file.download_to_drive(custom_path=local_path)

    await message.reply_text("⏳ در حال پردازش فایل، لطفاً چند لحظه صبر کنید...")

    try:
        if file_name.lower().endswith(".pdf"):
            text = extract_text_from_pdf(local_path)
        else:
            text = extract_text_from_image(local_path)

        if not text.strip():
            await message.reply_text("⚠️ هیچ متنی پیدا نشد.")
            return

        # اصلاح جهت راست به چپ برای فارسی/عربی
        text = text.replace("\n", " ")
        text = re.sub(r'\s+', ' ', text).strip()

        # تفکیک جدول‌ها
        parts = split_table_text(text)

        for part in parts:
            await message.reply_text(f"🧾 {part}", parse_mode="HTML")

    except Exception as e:
        logger.exception(f"Processing error: {e}")
        await message.reply_text("❌ خطایی هنگام پردازش فایل رخ داد.")

# =================== اجرای اصلی ===================
def main():
    threading.Thread(target=run_flask).start()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file))

    logger.info("🤖 Smart OCR Bot is running with uptime enabled...")
    app.run_polling()

if __name__ == "__main__":
    main()
