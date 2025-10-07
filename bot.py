import os
import tempfile
import logging
from pathlib import Path
from typing import Optional

import pytesseract
from PIL import Image
from pdf2image import convert_from_path
import fitz  # PyMuPDF

from telegram import Update, InputFile
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

# تنظیمات لاگ
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# متغیرهای محیطی
BOT_TOKEN = os.environ.get('BOT_TOKEN')
POPPLER_PATH = os.environ.get('POPPLER_PATH', '/usr/bin')


# استخراج متن دیجیتال از PDF
def extract_text_from_pdf_digital(pdf_path: str) -> str:
    try:
        text_chunks = []
        with fitz.open(pdf_path) as doc:
            for page in doc:
                text = page.get_text("text")
                if text:
                    text_chunks.append(text)
        return "\n\n".join(text_chunks).strip()
    except Exception as e:
        logger.exception("Error reading PDF with PyMuPDF: %s", e)
        return ""


# OCR برای PDF
def ocr_pdf_to_text(pdf_path: str, poppler_path: Optional[str] = None) -> str:
    try:
        images = convert_from_path(pdf_path, dpi=300, poppler_path=poppler_path)
    except Exception as e:
        logger.exception("Error converting PDF to images: %s", e)
        return ""

    texts = []
    for img in images:
        text = pytesseract.image_to_string(img, lang="fas+eng")
        texts.append(text)
    return "\n\n".join(texts).strip()


# OCR برای عکس‌ها
def ocr_image_to_text(image_path: str) -> str:
    try:
        img = Image.open(image_path)
        return pytesseract.image_to_string(img, lang="fas+eng")
    except Exception as e:
        logger.exception("Error running OCR on image: %s", e)
        return ""


# هندل فایل‌ها
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    if message.document:
        file_name = message.document.file_name or 'file'
        file_id = message.document.file_id
    elif message.photo:
        photo = message.photo[-1]
        file_id = photo.file_id
        file_name = f'photo_{photo.file_unique_id}.jpg'
    else:
        await message.reply_text('لطفاً یک فایل PDF یا عکس ارسال کنید.')
        return

    tmp_dir = tempfile.mkdtemp()
    try:
        file = await context.bot.get_file(file_id)
        local_path = os.path.join(tmp_dir, file_name)
        await file.download_to_drive(custom_path=local_path)

        if file_name.lower().endswith('.pdf'):
            await message.reply_text('📄 فایل PDF دریافت شد؛ در حال استخراج متن...')
            text = extract_text_from_pdf_digital(local_path)
            if not text.strip():
                await message.reply_text('متن دیجیتال پیدا نشد؛ در حال اجرای OCR...')
                text = ocr_pdf_to_text(local_path, poppler_path=POPPLER_PATH)
        else:
            await message.reply_text('🖼️ عکس دریافت شد؛ در حال اجرای OCR...')
            text = ocr_image_to_text(local_path)

        if not text.strip():
            await message.reply_text('⚠️ متنی پیدا نشد یا کیفیت پایین بود.')
            return

        # 🔹 ذخیره متن واقعی در فایل txt
        txt_filename = Path(file_name).stem + '.txt'
        out_txt = os.path.join(tmp_dir, txt_filename)
        with open(out_txt, 'w', encoding='utf-8') as f:
            f.write(text)  # ⚠️ اینجا متن واقعی ذخیره می‌شود

        # 🔹 ارسال فایل با اسم درست و بدون پیش‌نمایش
        await message.reply_document(
            document=InputFile(out_txt, filename=txt_filename),
            filename=txt_filename,
            caption="📎 فایل کامل متن استخراج‌شده"
        )

    except Exception as e:
        logger.exception('Error handling document: %s', e)
        await message.reply_text(f'⚠️ خطا در پردازش فایل: {str(e)}')

    finally:
        try:
            for p in Path(tmp_dir).glob('*'):
                p.unlink(missing_ok=True)
            Path(tmp_dir).rmdir()
        except Exception:
            pass


# فرمان استارت
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        'سلام 👋\n'
        'فایل PDF یا عکس بفرست تا متنش رو برات استخراج کنم 📄✨\n'
        'پشتیبانی از فارسی و انگلیسی ✅'
    )


# اجرای ربات
def main():
    if not BOT_TOKEN:
        raise RuntimeError('BOT_TOKEN environment variable not set.')

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler('start', start_cmd))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_document))
    logger.info('🤖 Bot started (polling)...')
    app.run_polling()


if __name__ == '__main__':
    main()
