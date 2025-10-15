# ===============================
# 🧠 پایه: نسخه سبک پایتون
# ===============================
FROM python:3.10-slim

# جلوگیری از ورودی تعاملی در زمان build
ENV DEBIAN_FRONTEND=noninteractive

# ===============================
# 🧩 نصب ابزارها و وابستگی‌های لازم OCR و Supervisor
# ===============================
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    libtesseract-dev \
    libgl1 \
    poppler-utils \
    ghostscript \
    wget \
    supervisor \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ===============================
# 📦 نصب زبان‌های OCR (فارسی، عربی، انگلیسی)
# ===============================
RUN set -eux; \
    mkdir -p /usr/share/tesseract-ocr/4.00/tessdata; \
    echo "📦 Downloading OCR language models..."; \
    wget -q -O /usr/share/tesseract-ocr/4.00/tessdata/fas.traineddata https://github.com/tesseract-ocr/tessdata_best/raw/main/fas.traineddata || true; \
    wget -q -O /usr/share/tesseract-ocr/4.00/tessdata/ara.traineddata https://github.com/tesseract-ocr/tessdata_best/raw/main/ara.traineddata || true; \
    wget -q -O /usr/share/tesseract-ocr/4.00/tessdata/eng.traineddata https://github.com/tesseract-ocr/tessdata_best/raw/main/eng.traineddata || true; \
    echo "✅ OCR traineddata files ready."

# ===============================
# 🧰 کپی فایل‌های پروژه به داخل کانتینر
# ===============================
WORKDIR /app
COPY . /app

# ===============================
# 📜 نصب کتابخانه‌های پایتون
# ===============================
RUN pip install --no-cache-dir \
    python-telegram-bot==20.3 \
    pytesseract \
    pdf2image \
    fitz \
    opencv-python-headless==4.8.1.78 \
    easyocr \
    numpy \
    Pillow \
    flask \
    arabic-reshaper \
    python-bidi

# ===============================
# ⚙️ تنظیم Supervisor برای مدیریت بات
# ===============================
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# ===============================
# 🌍 باز کردن پورت وب برای UptimeRobot
# ===============================
EXPOSE 8080

# ===============================
# 🚀 اجرای Supervisor (مدیریت بات)
# ===============================
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
