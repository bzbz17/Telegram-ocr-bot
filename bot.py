import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# ===============================
# 🔧 تنظیمات اولیه لاگ
# ===============================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===============================
# ⚙️ خواندن تنظیمات محیطی (Render)
# ===============================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
POPPLER_PATH = os.environ.get("POPPLER_PATH", "/usr/bin")
OCR_MAX_WORKERS = os.environ.get("OCR_MAX_WORKERS", "2")

logger.info("🔍 Environment variables loaded:")
logger.info(f"BOT_TOKEN: {'✅ Loaded' if BOT_TOKEN else '❌ MISSING!'}")
logger.info(f"POPPLER_PATH: {POPPLER_PATH}")
logger.info(f"OCR_MAX_WORKERS: {OCR_MAX_WORKERS}")

# ===============================
# 🚀 دستور استارت برای بررسی ربات
# ===============================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ ربات با موفقیت فعال شد!\n"
        "📄 لطفاً فایل PDF یا عکس ارسال کنید تا متن استخراج شود."
    )
    logger.info(f"✅ /start command received from user: {update.effective_user.first_name}")

# ===============================
# 📄 هندلر دریافت فایل یا عکس
# ===============================
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    await message.reply_text("📥 فایل دریافت شد. هنوز OCR در این نسخه غیرفعال است (برای تست توکن).")
    logger.info("📄 File received successfully.")

# ===============================
# 🧠 تابع اصلی
# ===============================
def main():
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN is missing! Please set it in Render environment variables.")
        raise SystemExit("BOT_TOKEN is missing!")

    try:
        app = ApplicationBuilder().token(BOT_TOKEN).build()
        logger.info("🤖 Telegram bot instance created successfully.")

        app.add_handler(CommandHandler("start", start))
        app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file))

        logger.info("✅ Bot handlers registered.")
        logger.info("🚀 Starting bot polling...")

        app.run_polling(stop_signals=None)
    except Exception as e:
        logger.exception(f"❌ Error while starting bot: {e}")

# ===============================
# ▶️ اجرای اصلی
# ===============================
if __name__ == "__main__":
    logger.info("📦 Launching Telegram OCR bot (DEBUG MODE)...")
    main()
