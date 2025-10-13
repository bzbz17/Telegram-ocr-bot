# ==========================
#  Base image
# ==========================
FROM python:3.10-slim

# جلوگیری از سوالات هنگام نصب
ENV DEBIAN_FRONTEND=noninteractive

# ==========================
# نصب ابزارهای OCR و وابستگی‌ها
# ==========================
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    tesseract-ocr \
    libtesseract-dev \
    libgl1 \
    poppler-utils \
    ghostscript \
    wget \
    supervisor \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ==========================
# دانلود مدل‌های OCR (fas, ara, eng)
# ==========================
RUN mkdir -p /usr/share/tesseract-ocr/4.00/tessdata && \
    cd /usr/share/tesseract-ocr/4.00/tessdata && \
    echo "📦 Downloading fast tessdata models..." && \
    wget -q -O fas.traineddata https://github.com/tesseract-ocr/tessdata_fast/raw/main/fas.traineddata && \
    wget -q -O ara.traineddata https://github.com/tesseract-ocr/tessdata_fast/raw/main/ara.traineddata && \
    wget -q -O eng.traineddata https://github.com/tesseract-ocr/tessdata_fast/raw/main/eng.traineddata && \
    echo "✅ OCR traineddata files ready."

# ==========================
# تنظیم پوشه کاری
# ==========================
WORKDIR /app
COPY . /app

# ==========================
# نصب کتابخانه‌های Python
# ==========================
RUN pip install --no-cache-dir -r requirements.txt

# ==========================
# Supervisor برای اجرای Flask و Bot
# ==========================
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# پورت برای Flask
EXPOSE 10000

# اجرای Supervisor
CMD ["supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
