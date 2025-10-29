import os
import tempfile
import logging
from pathlib import Path
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import pytesseract
from PIL import Image, ImageFilter, ImageEnhance, ImageOps
from pdf2image import convert_from_path
import fitz  # PyMuPDF
from flask import Flask

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# -----------------------
# تنظیمات و لاگ
# -----------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
POPPLER_PATH = os.environ.get("POPPLER_PATH", "/usr/bin")
MAX_WORKERS = int(os.environ.get("OCR_MAX_WORKERS", "4"))
executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

OCR_CONFIG = "--oem 3 --psm 6 -c preserve_interword_spaces=1"

# -----------------------
# Flask برای uptimerobot
# -----------------------
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "🤖 Telegram OCR Bot is Alive!", 200

# -----------------------
# پیش‌پردازش تصویر
# -----------------------
def preprocess_pil_image(img: Image.Image) -> Image.Image:
    try:
        img = img.convert("L")
        target_w = 1600
        if img.width < target_w:
            ratio = target_w / float(img.width)
            new_h = int(img.height * ratio)
            img = img.resize((target_w, new_h), Image.Resampling.BICUBIC)
        img = img.filter(ImageFilter.MedianFilter(size=3))
        img = ImageOps.autocontrast(img, cutoff=1)
        enhancer = ImageEnhance.Sharpness(img)
        img = enhancer.enhance(1.5)
        img = img.point(lambda p: 255 if p > 127 else 0)
        return img
    except Exception as e:
        logger.error(f"preprocess error: {e}")
        return img

# -----------------------
# تشخیص زبان تصویر
# -----------------------
def detect_language_from_image(image: Image.Image) -> str:
    try:
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
    except Exception:
        return "fas+eng"

# -----------------------
# استخراج متن PDF دیجیتال
# -----------------------
def extract_text_from_pdf_digital(pdf_path: str) -> str:
    texts = []
    try:
        with fitz.open(pdf_path) as doc:
            for page in doc:
                txt = page.get_text("text")
                if txt:
                    texts.append(txt)
    except Exception as e:
        logger.error(f"PDF text extract error: {e}")
    return "\n\n".join(texts).strip()

# -----------------------
# OCR تصویر
# -----------------------
def ocr_image_with_lang(img: Image.Image, lang: str) -> str:
    try:
        pre = preprocess_pil_image(img)
        return pytesseract.image_to_string(pre, lang=lang, config=OCR_CONFIG).strip()
    except Exception as e:
        logger.error(f"OCR error: {e}")
        return ""

# -----------------------
# OCR PDF چندصفحه‌ای
# -----------------------
def ocr_pdf_to_text(pdf_path: str, poppler_path=None) -> str:
    try:
        images = convert_from_path(pdf_path, dpi=300, poppler_path=poppler_path)
    except Exception as e:
        logger.error(f"PDF->image error: {e}")
        return ""

    def process_page(img):
        lang = detect_language_from_image(img)
        return ocr_image_with_lang(img, lang)

    futures = [executor.submit(process_page, img) for img in images]
    return "\n\n".join([f.result() for f in futures if f.result()])

# -----------------------
# نرمال‌سازی و تصحیح فارسی
# -----------------------
try:
    from hazm import Normalizer, WordTokenizer, POSTagger, Lemmatizer, SpellChecker
    normalizer = Normalizer()
    spell = SpellChecker()
    def normalize_text(text: str) -> str:
        text = normalizer.normalize(text)
        corrected = []
        for word in text.split():
            corrected.append(spell.correct(word))
        return " ".join(corrected)
except Exception:
    def normalize_text(text: str) -> str:
        return text.strip()

# -----------------------
# حذف webhook قبلی
# -----------------------
def ensure_delete_webhook(token: str):
    try:
        urllib.request.urlopen(f"https://api.telegram.org/bot{token}/deleteWebhook", timeout=10)
    except Exception:
        pass

# -----------------------
# هندل فایل‌ها
# -----------------------
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return

    if msg.document:
        file_id = msg.document.file_id
        file_name = msg.document.file_name or "file.pdf"
    elif msg.photo:
        file_id = msg.photo[-1].file_id
        file_name = f"{msg.photo[-1].file_unique_id}.jpg"
    else:
        await msg.reply_text("📎 لطفاً فایل PDF یا تصویر بفرست.")
        return

    tmp_dir = tempfile.mkdtemp()
    local_path = os.path.join(tmp_dir, file_name)

    try:
        tg_file = await context.bot.get_file(file_id)
        await tg_file.download_to_drive(custom_path=local_path)

        text = ""
        if file_name.lower().endswith(".pdf"):
            await msg.reply_text("📑 در حال استخراج متن از PDF ...")
            text = extract_text_from_pdf_digital(local_path)
            if not text.strip():
                await msg.reply_text("🔍 متن دیجیتال یافت نشد؛ اجرای OCR ...")
                text = ocr_pdf_to_text(local_path, poppler_path=POPPLER_PATH)
        else:
            await msg.reply_text("🖼️ در حال اجرای OCR روی تصویر ...")
            img = Image.open(local_path)
            lang = detect_language_from_image(img)
            text = ocr_image_with_lang(img, lang)

        if not text.strip():
            await msg.reply_text("⚠️ هیچ متنی یافت نشد.")
            return

        text = normalize_text(text)
        chunks = [text[i:i+3900] for i in range(0, len(text), 3900)]
        for chunk in chunks:
            await msg.reply_text(chunk)

        await msg.reply_text("✅ پردازش کامل شد.")
    except Exception as e:
        await msg.reply_text(f"❌ خطا: {e}")
    finally:
        for f in Path(tmp_dir).glob("*"):
            try:
                f.unlink()
            except Exception:
                pass
        try:
            Path(tmp_dir).rmdir()
        except Exception:
            pass

# -----------------------
# دستور /start
# -----------------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 سلام! من ربات OCR فارسی هستم.\nفقط یه عکس یا PDF بفرست تا متنش رو تحویلت بدم ✨")

# -----------------------
# اجرای همزمان Flask و Bot
# -----------------------
def main():
    ensure_delete_webhook(BOT_TOKEN)
    app_tg = ApplicationBuilder().token(BOT_TOKEN).build()
    app_tg.add_handler(CommandHandler("start", start_cmd))
    app_tg.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file))

    # اجرای همزمان Flask و Telegram
    import threading
    threading.Thread(target=lambda: flask_app.run(host="0.0.0.0", port=8080)).start()
    app_tg.run_polling()

if __name__ == "__main__":
    main()
