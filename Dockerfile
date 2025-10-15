FROM python:3.10-slim

WORKDIR /app

# نصب وابستگی‌های سیستم
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    libtesseract-dev \
    libgl1 \
    poppler-utils \
    ghostscript \
    wget \
    supervisor \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# دانلود مدل‌های دقیق (best)
RUN mkdir -p /usr/share/tesseract-ocr/4.00/tessdata && \
    cd /usr/share/tesseract-ocr/4.00/tessdata && \
    echo "📦 Downloading best tessdata models..." && \
    wget -q -O fas.traineddata https://github.com/tesseract-ocr/tessdata_best/raw/main/fas.traineddata && \
    wget -q -O ara.traineddata https://github.com/tesseract-ocr/tessdata_best/raw/main/ara.traineddata && \
    wget -q -O eng.traineddata https://github.com/tesseract-ocr/tessdata_best/raw/main/eng.traineddata && \
    echo "✅ High-quality OCR traineddata files ready."

# نصب پکیج‌های پایتون
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# کپی فایل‌های پروژه
COPY . .

# Supervisor برای نگه داشتن ربات در UptimeRobot
CMD ["supervisord", "-c", "/app/supervisord.conf"]
