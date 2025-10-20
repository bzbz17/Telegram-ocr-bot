# ===============================
# Stage 1: Base
# ===============================
FROM python:3.10-slim

# جلوگیری از بافر شدن لاگ‌ها
ENV PYTHONUNBUFFERED=1

# نصب پکیج‌های سیستمی لازم برای OCR
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-fas \
    tesseract-ocr-ara \
    tesseract-ocr-eng \
    libgl1 \
    poppler-utils \
    ghostscript \
    wget \
    supervisor \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ===============================
# نصب پکیج‌های پایتون
# ===============================
WORKDIR /app
COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# ===============================
# کپی سورس پروژه
# ===============================
COPY . .

# ===============================
# پورت Flask
# ===============================
EXPOSE 8080

# ===============================
# اجرای supervisord برای بالا ماندن دائمی ربات
# ===============================
CMD ["python3", "bot.py"]
