# Telegram OCR Bot

این ربات فایل‌های PDF و عکس رو می‌گیره و متن داخلش رو استخراج می‌کنه و به صورت `.txt` برمی‌گردونه.  
از OCR فارسی + انگلیسی پشتیبانی می‌کنه.

---

## 🚀 Deploy روی Railway

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new/template?template=https://github.com/bzbz17/Telegram-ocr-bot&envs=BOT_TOKEN,POPPLER_PATH&BOT_TOKENDesc=Telegram+Bot+Token+from+BotFather&POPPLER_PATHDesc=Optional+Poppler+path+(usually+/usr/bin))

1. روی دکمه بالا بزن.  
2. در بخش Environment Variable مقدار `BOT_TOKEN` رو وارد کن.  
3. Deploy کن.  
4. رباتت آماده‌ست!  

---

## 📦 Requirements
- Python 3.11
- Tesseract OCR (fas+eng)
- Poppler-utils
