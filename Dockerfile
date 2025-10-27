# --------------------------
#   Telegram OCR Bot (Render)
# --------------------------

FROM python:3.10-slim

# جلوگیری از بافر لاگ
ENV PYTHONUNBUFFERED=1

# نصب وابستگی‌های سیستمی
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-fas \
    tesseract-ocr-ara \
    libgl1 \
    poppler-utils \
    ghostscript \
    wget \
    supervisor \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

# تنظیم دایرکتوری کاری
WORKDIR /app

# کپی فایل‌های پروژه
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY . .

# پورت Flask
EXPOSE 8080

# اجرای supervisor
CMD ["supervisord", "-c", "/app/supervisord.conf"]
