FROM python:3.10-slim

# نصب وابستگی‌ها
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-fas \
    tesseract-ocr-ara \
    tesseract-ocr-eng \
    libgl1 \
    poppler-utils \
    ghostscript \
    wget \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# نصب پکیج‌های پایتون
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# کپی فایل‌های پروژه
COPY . .

# اجرای ربات
CMD ["python", "bot.py"]
