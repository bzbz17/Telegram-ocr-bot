# =======================================
# 🧠 پایه‌ی سبک پایتون برای ربات تلگرام OCR
# =======================================
FROM python:3.10-slim

# جلوگیری از ورودی تعاملی در زمان build
ENV DEBIAN_FRONTEND=noninteractive

# =======================================
# 🧰 نصب ابزارهای لازم برای OCR و Supervisor
# =======================================
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    libtesseract-dev \
    libgl1 \
    poppler-utils \
    ghostscript \
    wget \
    supervisor \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# =======================================
# 📦 نصب زبان‌های OCR فارسی، عربی و انگلیسی
# =======================================
RUN set -eux; \
    mkdir -p /usr/share/tesseract-ocr/4.00/tessdata; \
    echo "📦 Downloading OCR language models..."; \
    wget -q -O /usr/share/tesseract-ocr/4.00/tessdata/fas.traineddata https://github.com/tesseract-ocr/tessdata_best/raw/main/fas.traineddata || true; \
    wget -q -O /usr/share/tesseract-ocr/4.00/tessdata/ara.traineddata https://github.com/tesseract-ocr/tessdata_best/raw/main/ara.traineddata || true; \
    wget -q -O /usr/share/tesseract-ocr/4.00/tessdata/eng.traineddata https://github.com/tesseract-ocr/tessdata_best/raw/main/eng.traineddata || true; \
    echo "✅ OCR traineddata files ready."

# =======================================
# 📂 کپی فایل‌های پروژه به مسیر /app
# =======================================
WORKDIR /app
COPY . /app

# =======================================
# 📜 نصب کتابخانه‌های پایتون با نسخه‌های سازگار
# =======================================
RUN pip install --no-cache-dir \
    numpy==1.26.4 \
    python-telegram-bot==20.3 \
    pytesseract \
    pdf2image \
    PyMuPDF==1.24.9 \
    opencv-python-headless==4.8.1.78 \
    easyocr==1.7.1 \
    Pillow==10.3.0 \
    flask \
    arabic-reshaper \
    python-bidi

# =======================================
# ⚙️ Supervisor برای اجرای پایدار ربات
# =======================================
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# =======================================
# 🌍 پورت Flask برای پینگ UptimeRobot
# =======================================
EXPOSE 8080

# =======================================
# 🚀 اجرای Supervisor
# =======================================
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
