# Telegram OCR Bot (Render Version)

این ربات فایل‌های PDF و عکس رو می‌گیره و متنش رو به صورت `.txt` برمی‌گردونه.
از OCR فارسی و انگلیسی پشتیبانی می‌کنه.

---

## 🚀 اجرای پروژه در Render

1. وارد [render.com](https://render.com) شو.
2. New → Web Service رو بزن.
3. ریپوی GitHub خودت رو انتخاب کن.
4. محیط رو روی **Docker** بذار.
5. توی Environment Variable‌ها مقدار زیر رو وارد کن:

| Name | Value |
|------|--------|
| BOT_TOKEN | توکن ربات تلگرام از BotFather |
| POPPLER_PATH | /usr/bin |

6. Deploy رو بزن ✅

بعد از اتمام Deploy، ربات به‌صورت خودکار روشن میشه.
