# ==========================
#  Base image سبک و امن
# ==========================
FROM python:3.10-slim

ENV DEBIAN_FRONTEND=noninteractive

# ==========================
# نصب ابزارهای OCR و وابستگی‌ها
# ==========================
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    libtesseract-dev \
    libgl1 \
    poppler-utils \
    ghostscript \
    wget \
    supervisor \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ==========================
# دانلود مدل‌های OCR سریع
# ==========================
RUN mkdir -p /usr/share/tesseract-ocr/4.00/tessdata && \
    cd /usr/share/tesseract-ocr/4.00/tessdata && \
    echo "📦 Downloading fast tessdata models..." && \
    wget -q -O fas.traineddata https://github.com/tesseract-ocr/tessdata_fast/raw/main/fas.traineddata && \
    wget -q -O ara.traineddata https://github.com/tesseract-ocr/tessdata_fast/raw/main/ara.traineddata && \
    wget -q -O eng.traineddata https://github.com/tesseract-ocr/tessdata_fast/raw/main/eng.traineddata && \
    echo "✅ OCR traineddata files ready."

# ==========================
# پوشه کاری و کپی فایل‌ها
# ==========================
WORKDIR /app
COPY . /app

# ==========================
# نصب پکیج‌های Python
# ==========================
RUN pip install --no-cache-dir -r requirements.txt

# ==========================
# Supervisor برای اجرای Flask و Bot
# ==========================
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

EXPOSE 10000

CMD ["supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
