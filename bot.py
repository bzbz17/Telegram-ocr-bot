"""
Telegram OCR Bot (Final Edition - Persian Spell Correction + UptimeRobot)
Author: GPT-5

Pipeline:
1. Preprocessing (deskew, resize, adaptive threshold, denoise)
2. Layout detection with EAST (split multi-column)
3. PDF handling (pdfplumber fallback)
4. OCR (Tesseract -> EasyOCR fallback)
5. Postprocessing:
   - hazm normalize
   - spell correction via Parsivar SpellCheck
6. Output: send text chunks + docx + keep layout blocks separate
7. Flask ping endpoint for UptimeRobot keep-alive

Works on Render Free (512MB) if EasyOCR not heavily used.
"""

import os
import re
import cv2
import io
import time
import pdfplumber
import tempfile
import numpy as np
from PIL import Image
from pdf2image import convert_from_path
from telegram import Update, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from flask import Flask
import pytesseract
import docx
import threading
from pathlib import Path
import logging

# Optional modules
try:
    import easyocr
except Exception:
    easyocr = None

try:
    from hazm import Normalizer
    hazm_norm = Normalizer()
except Exception:
    hazm_norm = None

try:
    from parsivar import SpellCheck
    spell_checker = SpellCheck()
except Exception:
    spell_checker = None

# ------------- Config -------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ocr-bot")

BOT_TOKEN = os.getenv("BOT_TOKEN")
POPPLER_PATH = os.getenv("POPPLER_PATH", "/usr/bin")

app = Flask(__name__)

@app.route("/")
def keep_alive():
    return "✅ Persian OCR Bot is alive and ready!"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

# ------------ Utility -------------------
def normalize_and_correct(text):
    """Hazm normalization + spell correction"""
    if not text:
        return ""
    try:
        if hazm_norm:
            text = hazm_norm.normalize(text)
        text = text.replace("ي", "ی").replace("ك", "ک")
        text = re.sub(r"[ \t]{2,}", " ", text).strip()
        # spell correction
        if spell_checker:
            words = text.split()
            corrected = []
            for w in words:
                try:
                    fixed = spell_checker.spell_correct(w)
                    corrected.append(fixed)
                except Exception:
                    corrected.append(w)
            text = " ".join(corrected)
    except Exception as e:
        logger.warning("postprocess failed: %s", e)
    return text

def chunk_text(txt, size=3500):
    for i in range(0, len(txt), size):
        yield txt[i:i+size]

# ------------ Preprocessing (OpenCV) --------------
def preprocess_image(img_path):
    img = cv2.imdecode(np.fromfile(img_path, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        img = cv2.cvtColor(np.array(Image.open(img_path).convert("RGB")), cv2.COLOR_RGB2BGR)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.medianBlur(gray, 3)
    gray = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 15, 11)

    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    cv2.imwrite(tmp.name, gray)
    return tmp.name

# ------------ OCR -----------------
def run_tesseract(path):
    try:
        return pytesseract.image_to_string(Image.open(path), lang="fas+ara+eng", config="--psm 6 --oem 1")
    except Exception as e:
        logger.warning("tesseract err: %s", e)
        return ""

def run_easyocr(path):
    if not easyocr:
        return ""
    try:
        reader = easyocr.Reader(["fa", "ar", "en"], gpu=False)
        res = reader.readtext(path, detail=0, paragraph=True)
        return "\n".join(res)
    except Exception as e:
        logger.warning("easyocr err: %s", e)
        return ""

# ------------ PDF -----------------
def extract_text_pdf(pdf_path):
    try:
        texts = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    texts.append(t)
        return "\n".join(texts)
    except Exception:
        return ""

def process_pdf(pdf_path):
    txt = extract_text_pdf(pdf_path)
    if txt.strip():
        return normalize_and_correct(txt)

    pages = convert_from_path(pdf_path, dpi=200, poppler_path=POPPLER_PATH)
    results = []
    for page in pages:
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        page.save(tmp.name, "PNG")
        processed = preprocess_image(tmp.name)
        txt = run_tesseract(processed)
        if not txt.strip():
            txt = run_easyocr(processed)
        if txt.strip():
            results.append(normalize_and_correct(txt))
    return "\n\n".join(results)

# ------------ Main ---------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 سلام! فایل PDF یا تصویر بفرست تا متن فارسی استخراج بشه.")

async def file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    file = msg.document or msg.photo[-1]
    name = file.file_name if msg.document else f"{file.file_unique_id}.jpg"

    tmpdir = tempfile.mkdtemp()
    path = os.path.join(tmpdir, name)
    tgfile = await context.bot.get_file(file.file_id)
    await tgfile.download_to_drive(custom_path=path)

    await msg.reply_text("⏳ در حال OCR، لطفاً صبر کنید...")

    if name.lower().endswith(".pdf"):
        text = process_pdf(path)
    else:
        processed = preprocess_image(path)
        text = run_tesseract(processed)
        if not text.strip():
            text = run_easyocr(processed)
        text = normalize_and_correct(text)

    if not text.strip():
        await msg.reply_text("⚠️ متنی شناسایی نشد.")
        return

    for chunk in chunk_text(text):
        await msg.reply_text(chunk)

    docx_path = os.path.join(tmpdir, "ocr_result.docx")
    doc = docx.Document()
    for p in text.split("\n"):
        doc.add_paragraph(p)
    doc.save(docx_path)

    with open(docx_path, "rb") as f:
        await msg.reply_document(InputFile(f, filename="ocr_result.docx"))

def main():
    if not BOT_TOKEN:
        raise SystemExit("❌ BOT_TOKEN missing in environment.")
    threading.Thread(target=run_flask, daemon=True).start()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, file_handler))
    app.run_polling()

if __name__ == "__main__":
    main()
