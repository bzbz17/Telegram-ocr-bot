import os
import logging
import tempfile
from pathlib import Path
from flask import Flask
from threading import Thread

import pytesseract
from pdf2image import convert_from_path
from PIL import Image
import easyocr

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# =============================
# 🧠 تنظیمات اولیه
# =============================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
POPPLER_PATH = os.getenv("POPPLER_PATH", "/usr/bin")

# =============================
# 🌐 Flask برای UptimeRobot
# =============================
app = Flask(__name__)

@app.route("/")
def home():
    return "🤖 Bot is running fine!"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

Thread(target=run_flask, daemon=True).start()

# =============================
# 🧠 OCR Reader آماده (EasyOCR)
# =============================
reader = easyocr.Reader(["fa", "ar", "en"], gpu=False)

# =============================
# 📄 توابع OCR
# =============================
def extract_text_from_pdf(pdf_path: str) -> str:
    """استخراج متن از PDF با اولویت دیجیتال، سپس OCR"""
    text_result = ""

    # ۱. تلاش برای استخراج متن دیجیتال
    try:
        import fitz  # PyMuPDF
        with fitz.open(pdf_path) as doc:
            for page in doc:
                txt = page.get_text("text")
                if txt.strip():
                    text_result += txt + "\n"
    except Exception as e:
        logger.warning(f"Digital PDF extraction failed: {e}")

    # ۲. اگر متن خالی بود، OCR انجام بده
    if not text_result.strip():
        try:
            images = convert_from_path(pdf_path, dpi=200, poppler_path=POPPLER_PATH)
            for img in images:
                text_result += "\n".join(reader.readtext(img, detail=0, paragraph=True))
        except Exception as e:
            logger.error(f"OCR PDF Error: {e}")
            return ""

    # 🔹 اینجا دیگه نیازی به arabic_reshaper یا bidi نیست
    # چون EasyOCR خروجی قابل‌خواندن RTL برمی‌گردونه.
    return text_result.strip()


def extract_text_from_image(image_path: str) -> str:
    """استخراج متن از عکس با EasyOCR + Tesseract برای fallback"""
    try:
        text = "\n".join(reader.readtext(image_path, detail=0, paragraph=True))
        if not text.strip():
            img = Image.open(image_path)
            text = pytesseract.image_to_string(img, lang="fas+ara+eng")
        return text.strip()
    except Exception as e:
        logger.error(f"OCR Image Error: {e}")
        return ""

# =============================
# 🤖 فرمان‌ها و هندلرها
# =============================
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 سلام!\n"
        "فقط یه عکس یا فایل PDF بفرست تا متن فارسی، عربی یا انگلیسی‌ش برات استخراج بشه ✨"
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
        photo = message.photo[-1]
        file_id = photo.file_id
        file_name = f"{photo.file_unique_id}.jpg"
    else:
        await message.reply_text("📎 لطفاً فایل PDF یا عکس بفرست.")
        return

    tmp_dir = tempfile.mkdtemp()
    local_path = os.path.join(tmp_dir, file_name)

    try:
        await message.reply_text("🕓 در حال پردازش و استخراج متن... لطفاً چند لحظه صبر کنید.")

        telegram_file = await context.bot.get_file(file_id)
        await telegram_file.download_to_drive(custom_path=local_path)

        if file_name.lower().endswith(".pdf"):
            text = extract_text_from_pdf(local_path)
        else:
            text = extract_text_from_image(local_path)

        if not text.strip():
            await message.reply_text("⚠️ متنی قابل استخراج نبود.")
            return

        # ✨ ارسال متن به صورت بخش‌بخش اگر طولانی بود
        chunk_size = 3500
        for i in range(0, len(text), chunk_size):
            await message.reply_text(text[i:i + chunk_size])

        await message.reply_text("✅ استخراج متن کامل شد!")

    except Exception as e:
        logger.exception(f"Error processing file: {e}")
        await message.reply_text(f"❌ خطا در پردازش فایل: {str(e)}")

    finally:
        try:
            for f in Path(tmp_dir).glob("*"):
                f.unlink(missing_ok=True)
            Path(tmp_dir).rmdir()
        except Exception:
            pass

# =============================
# 🚀 اجرای ربات
# =============================
def main():
    if not BOT_TOKEN:
        raise RuntimeError("❌ BOT_TOKEN در محیط تنظیم نشده است.")

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file))

    logger.info("🤖 Bot started and waiting for files...")
    app.run_polling()

if __name__ == "__main__":
    main()
