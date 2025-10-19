import os
import tempfile
import logging
import threading
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from pdf2image import convert_from_path
from PIL import Image
import pytesseract
from cleantext import clean

# ================== تنظیمات پایه ==================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
POPPLER_PATH = os.environ.get("POPPLER_PATH", "/usr/bin")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================== Flask برای UptimeRobot ==================
app = Flask(__name__)

@app.route("/")
def home():
    return "✅ OCR Bot is alive and running!"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

# ================== پردازش OCR ==================
def preprocess_text(text):
    """نرمال‌سازی و پاکسازی متن فارسی"""
    return clean(
        text,
        fix_unicode=True,
        to_ascii=False,
        lower=False,
        no_line_breaks=False,
        keep_two_line_breaks=True
    )

def extract_text_from_image(image_path):
    """استخراج متن از عکس"""
    text = pytesseract.image_to_string(Image.open(image_path), lang="fas+ara+eng")
    return preprocess_text(text.strip())

def extract_text_from_pdf(pdf_path):
    """استخراج متن از PDF (OCR در صورت اسکن بودن)"""
    text_result = []
    images = convert_from_path(pdf_path, dpi=250, poppler_path=POPPLER_PATH)
    for img in images:
        temp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        img.save(temp.name, "PNG")
        text = extract_text_from_image(temp.name)
        text_result.append(text)
    return "\n\n--- صفحه جدید ---\n\n".join(text_result).strip()

# ================== دستورات ربات ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 سلام! من ربات OCR هستم.\n\n"
        "📄 فایل PDF یا عکس بفرست تا متن فارسی، عربی یا انگلیسی‌اش رو برات بنویسم.\n"
        "📌 جهت متن راست‌به‌چپ و جدول‌ها تا حد ممکن حفظ می‌شود."
    )

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    file_id, file_name = None, None

    if message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name
    elif message.photo:
        file_id = message.photo[-1].file_id
        file_name = f"{file_id}.jpg"
    else:
        await message.reply_text("📎 لطفاً فایل PDF یا عکس ارسال کنید.")
        return

    tmp_dir = tempfile.mkdtemp()
    local_path = os.path.join(tmp_dir, file_name)
    telegram_file = await context.bot.get_file(file_id)
    await telegram_file.download_to_drive(custom_path=local_path)

    await message.reply_text("⏳ در حال استخراج متن، لطفاً چند لحظه صبر کنید...")

    try:
        if file_name.lower().endswith(".pdf"):
            text = extract_text_from_pdf(local_path)
        else:
            text = extract_text_from_image(local_path)

        if not text.strip():
            await message.reply_text("⚠️ متنی شناسایی نشد.")
            return

        # تقسیم متن در پیام‌های چندبخشی (برای محدودیت تلگرام)
        parts = [text[i:i+3500] for i in range(0, len(text), 3500)]
        for part in parts:
            await message.reply_text(f"📝 {part}")

    except Exception as e:
        logger.error(f"Error: {e}")
        await message.reply_text("❌ خطایی هنگام پردازش فایل رخ داد.")

# ================== اجرای ربات ==================
def main():
    threading.Thread(target=run_flask).start()

    app_bot = ApplicationBuilder().token(BOT_TOKEN).build()
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file))

    logger.info("🤖 OCR Bot started successfully (UptimeRobot active)...")
    app_bot.run_polling()

if __name__ == "__main__":
    main()
