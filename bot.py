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

# =============== تنظیمات پایه ===============
BOT_TOKEN = os.environ.get("BOT_TOKEN")
POPPLER_PATH = os.environ.get("POPPLER_PATH", "/usr/bin")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============== Flask برای UptimeRobot ===============
app = Flask(__name__)

@app.route("/")
def home():
    return "✅ OCR bot is alive and running!"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

# =============== تابع OCR از تصویر ===============
def extract_text_from_image(image_path):
    """تبدیل تصویر به متن فارسی/عربی/انگلیسی"""
    text = pytesseract.image_to_string(Image.open(image_path), lang="fas+ara+eng")
    return text.strip()

# =============== تابع OCR از PDF ===============
def extract_text_from_pdf(pdf_path):
    """تبدیل PDF به متن فارسی/عربی/انگلیسی"""
    text_result = []
    images = convert_from_path(pdf_path, dpi=250, poppler_path=POPPLER_PATH)
    for img in images:
        temp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        img.save(temp.name, "PNG")
        text = extract_text_from_image(temp.name)
        text_result.append(text)
    return "\n".join(text_result).strip()

# =============== دستورات تلگرام ===============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 سلام! من ربات OCR هستم.\n\n"
        "فقط کافیه فایل PDF یا عکس بفرستی تا متنش (فارسی، عربی، انگلیسی) رو برات بنویسم ✅"
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

        await message.reply_text(f"📝 نتیجه OCR:\n\n{text}")

    except Exception as e:
        logger.error(f"Error: {e}")
        await message.reply_text("❌ خطایی هنگام پردازش فایل رخ داد.")

# =============== اجرای اصلی ===============
def main():
    threading.Thread(target=run_flask).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file))

    logger.info("🤖 OCR Bot is running (UptimeRobot active)...")
    app.run_polling()

if __name__ == "__main__":
    main()
