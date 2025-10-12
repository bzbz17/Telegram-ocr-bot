# =============================================================
# 🤖 bot.py — OCR هوشمند + پینگ Flask برای UptimeRobot
# =============================================================

import os
import tempfile
import logging
import re
import asyncio
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
from threading import Thread

import pytesseract
import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageOps
from pdf2image import convert_from_path
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# ----------------------------
# تنظیمات عمومی
# ----------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
POPPLER_PATH = os.environ.get("POPPLER_PATH", "/usr/bin")

MAX_WORKERS = int(os.environ.get("OCR_MAX_WORKERS", "6"))
executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

OCR_CONFIG = "--oem 3 --psm 6 -c preserve_interword_spaces=1 --tessdata-dir /usr/share/tesseract-ocr/4.00/tessdata"

# ----------------------------
# 🧠 تشخیص دست‌نویس یا تایپ‌شده
# ----------------------------
def detect_handwritten(image: np.ndarray) -> bool:
    try:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)
        density = np.sum(edges > 0) / edges.size
        return density > 0.05
    except Exception:
        return False


# ----------------------------
# 🧩 پیش‌پردازش تصویر
# ----------------------------
def preprocess_image(img: Image.Image, handwritten: bool = False) -> Image.Image:
    img = img.convert("L")
    if img.width < 1000:
        scale = 1000 / img.width
        img = img.resize((int(img.width * scale), int(img.height * scale)), Image.Resampling.LANCZOS)
    img = ImageOps.autocontrast(img, cutoff=2)
    if handwritten:
        img = ImageEnhance.Contrast(img).enhance(2.0)
        img = ImageEnhance.Sharpness(img).enhance(1.8)
    else:
        img = ImageEnhance.Contrast(img).enhance(1.4)
        img = ImageEnhance.Sharpness(img).enhance(1.2)
    img = img.point(lambda x: 255 if x > 160 else 0, mode="1")
    return img


# ----------------------------
# 🌐 تشخیص زبان
# ----------------------------
def detect_language(image: Image.Image) -> str:
    try:
        txt = pytesseract.image_to_string(image, lang="fas+eng", config="--psm 6")
        farsi = len(re.findall(r'[\u0600-\u06FF]', txt))
        english = len(re.findall(r'[A-Za-z]', txt))
        return "fas_fast+eng" if farsi > english else "eng"
    except Exception:
        return "fas_fast+eng"


# ----------------------------
# 🔍 OCR تصویر
# ----------------------------
def ocr_image_to_text(img: Image.Image, lang: str, handwritten: bool) -> str:
    processed = preprocess_image(img, handwritten)
    data = pytesseract.image_to_data(
        processed, lang=lang, config=OCR_CONFIG, output_type=pytesseract.Output.DICT
    )

    lines = {}
    for i, text in enumerate(data["text"]):
        if not text.strip():
            continue
        y = data["top"][i]
        line_key = round(y / 40)
        lines.setdefault(line_key, []).append((data["left"][i], text))

    full_text = []
    for _, words in sorted(lines.items()):
        words = sorted(words, key=lambda x: x[0], reverse=True)
        line = " ".join(w for _, w in words)
        full_text.append(line)

    text = "\n".join(full_text).strip()
    text = text.replace("ي", "ی").replace("ك", "ک")
    return text


# ----------------------------
# 📄 OCR PDF
# ----------------------------
def ocr_pdf_to_text(pdf_path: str, poppler_path: Optional[str] = None) -> str:
    images = convert_from_path(pdf_path, dpi=200, poppler_path=poppler_path)
    results = []

    for img in images:
        np_img = np.array(img)
        handwritten = detect_handwritten(np_img)
        lang = detect_language(img)
        text = ocr_image_to_text(img, lang, handwritten)
        results.append(text)

    return "\n\n".join(results).strip()


# ----------------------------
# 📨 فایل دریافتی از تلگرام
# ----------------------------
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
        await msg.reply_text("📄 لطفاً یک فایل PDF یا عکس بفرست.")
        return

    tmp_dir = tempfile.mkdtemp()
    local_path = os.path.join(tmp_dir, file_name)

    try:
        file = await context.bot.get_file(file_id)
        await file.download_to_drive(custom_path=local_path)
        await msg.reply_text("⏳ در حال پردازش هوشمند OCR ...")

        def process():
            if file_name.lower().endswith(".pdf"):
                return ocr_pdf_to_text(local_path, poppler_path=POPPLER_PATH)
            else:
                img = Image.open(local_path)
                np_img = np.array(img)
                handwritten = detect_handwritten(np_img)
                lang = detect_language(img)
                return ocr_image_to_text(img, lang, handwritten)

        loop = asyncio.get_running_loop()
        text = await loop.run_in_executor(executor, process)

        if not text.strip():
            await msg.reply_text("⚠️ متنی پیدا نشد.")
            return

        for i in range(0, len(text), 4000):
            await msg.reply_text(text[i:i + 4000])

        await msg.reply_text("✅ استخراج متن با موفقیت انجام شد.")
    except Exception as e:
        logger.exception(e)
        await msg.reply_text(f"❌ خطا در پردازش: {str(e)}")
    finally:
        for f in Path(tmp_dir).glob("*"):
            f.unlink(missing_ok=True)
        Path(tmp_dir).rmdir()


# ----------------------------
# 🚀 فرمان شروع
# ----------------------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 سلام!\nمن ربات OCR هوشمند هستم 📑\n"
        "فایل PDF یا عکس بفرست تا متن تایپ‌شده یا دست‌نویسش رو برات استخراج کنم ✨"
    )


# ----------------------------
# 🌐 Flask Ping Server برای UptimeRobot
# ----------------------------
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "✅ Bot is alive!", 200


def run_flask():
    flask_app.run(host="0.0.0.0", port=10000)


# ----------------------------
# 🧠 اجرای همزمان Flask و Bot
# ----------------------------
def main():
    if not BOT_TOKEN:
        raise RuntimeError("❌ BOT_TOKEN تعریف نشده!")

    # اجرای Flask در Thread جدا برای پینگ UptimeRobot
    Thread(target=run_flask).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file))

    logger.info("🤖 Smart OCR Bot started with Flask keep-alive ...")
    app.run_polling()


if __name__ == "__main__":
    main()
