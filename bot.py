import os
import tempfile
import logging
from pathlib import Path
from typing import Optional
import re
import urllib.request
import threading
from flask import Flask

import pytesseract
from PIL import Image, ImageFilter, ImageEnhance, ImageOps
from pdf2image import convert_from_path
import fitz  # PyMuPDF
from concurrent.futures import ThreadPoolExecutor
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# ---------- Logging ----------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
POPPLER_PATH = os.environ.get("POPPLER_PATH", "/usr/bin")
MAX_WORKERS = int(os.environ.get("OCR_MAX_WORKERS", "4"))
executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

OCR_CONFIG = "--oem 3 --psm 6 -c preserve_interword_spaces=1"

# ---------- Flask Keepalive ----------
app = Flask(__name__)

@app.route("/")
def home():
    return "🤖 Bot is alive!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# ---------- Image Preprocessing ----------
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
        logger.exception(f"preprocess error: {e}")
        return img

# ---------- Language Detection ----------
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
    except Exception as e:
        logger.error(f"language detect error: {e}")
        return "fas+eng"

# ---------- OCR Processing ----------
def extract_text_from_pdf_digital(pdf_path: str) -> str:
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
    try:
        pre = preprocess_pil_image(img)
        return pytesseract.image_to_string(pre, lang=lang, config=OCR_CONFIG).strip()
    except Exception as e:
        logger.exception(f"OCR image error: {e}")
        return ""

def ocr_pdf_to_text(pdf_path: str, poppler_path: Optional[str] = None) -> str:
    try:
        images = convert_from_path(pdf_path, dpi=300, poppler_path=poppler_path)
    except Exception as e:
        logger.exception(f"pdf->image error: {e}")
        return ""
    def process_page(img):
        try:
            lang = detect_language_from_image(img)
            return ocr_image_with_lang(img, lang)
        except Exception as e:
            logger.exception(f"page process error: {e}")
            return ""
    futures = [executor.submit(process_page, img.copy()) for img in images]
    results = [f.result() for f in futures]
    texts = [r for r in results if r]
    return "\n\n".join(texts).strip()

def ensure_delete_webhook(token: str):
    try:
        url = f"https://api.telegram.org/bot{token}/deleteWebhook"
        urllib.request.urlopen(url, timeout=10)
    except Exception:
        pass

# ---------- Telegram Handlers ----------
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return
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
        tg_file = await context.bot.get_file(file_id)
        await tg_file.download_to_drive(custom_path=local_path)
        text = ""
        if file_name.lower().endswith(".pdf"):
            await message.reply_text("📑 در حال استخراج متن از PDF ...")
            text = extract_text_from_pdf_digital(local_path)
            if not text.strip():
                await message.reply_text("🔍 اجرای OCR روی صفحات ...")
                text = ocr_pdf_to_text(local_path, poppler_path=POPPLER_PATH)
        else:
            await message.reply_text("🖼️ در حال اجرای OCR روی تصویر ...")
            img = Image.open(local_path)
            lang = detect_language_from_image(img)
            text = ocr_image_with_lang(img, lang)
        if not text.strip():
            await message.reply_text("⚠️ هیچ متنی قابل استخراج نبود.")
            return
        text = text.strip()
        max_len = 3900
        for i in range(0, len(text), max_len):
            await message.reply_text(text[i:i + max_len])
        await message.reply_text("✅ استخراج متن با موفقیت انجام شد.")
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

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 سلام!\n"
        "من ربات OCR هستم.\n"
        "📄 یک PDF یا عکس بفرست تا متنش رو برات استخراج کنم."
    )

# ---------- Main ----------
def main():
    if not BOT_TOKEN:
        raise RuntimeError("❌ BOT_TOKEN is missing!")

    ensure_delete_webhook(BOT_TOKEN)
    app_tg = ApplicationBuilder().token(BOT_TOKEN).build()
    app_tg.add_handler(CommandHandler("start", start_cmd))
    app_tg.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file))

    threading.Thread(target=run_flask, daemon=True).start()
    app_tg.run_polling()

if __name__ == "__main__":
    main()
