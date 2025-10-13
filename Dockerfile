# ==========================
#  Base image: سبک و سریع
# ==========================
FROM python:3.10-slim

# جلوگیری از سوالات نصب
ENV DEBIAN_FRONTEND=noninteractive

# ==========================
# نصب ابزارهای OCR و وابستگی‌ها
# ==========================
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-fas \
    tesseract-ocr-ara \
    tesseract-ocr-eng \
    libgl1-mesa-glx \
    poppler-utils \
    ghostscript \
    wget \
    supervisor \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ==========================
# مسیر مدل‌ها و دانلود tessdata_fast
# ==========================
RUN mkdir -p /usr/share/tesseract-ocr/4.00/tessdata && \
    cd /usr/share/tesseract-ocr/4.00/tessdata && \
    echo "📦 Downloading fast OCR models..." && \
    wget -q -O fas.traineddata https://github.com/tesseract-ocr/tessdata_fast/raw/main/fas.traineddata && \
    wget -q -O ara.traineddata https://github.com/tesseract-ocr/tessdata_fast/raw/main/ara.traineddata && \
    wget -q -O eng.traineddata https://github.com/tesseract-ocr/tessdata_fast/raw/main/eng.traineddata && \
    echo "✅ OCR traineddata files ready."

# ==========================
# کپی فایل‌های پروژه
# ==========================
WORKDIR /app
COPY . /app

# ==========================
# نصب وابستگی‌های پایتون
# ==========================
RUN pip install --no-cache-dir -r requirements.txt

# ==========================
# Supervisor برای اجرای Flask + Bot
# ==========================
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# پورت برای Flask (UptimeRobot)
EXPOSE 10000

# اجرای Supervisor
CMD ["supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
