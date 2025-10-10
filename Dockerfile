# =======================================================
# 🧠 Dockerfile — OCR فارسی/عربی/انگلیسی با مدل‌های BEST
# نسخه پایدار برای Render (دانلود مدل‌ها هنگام اجرا)
# =======================================================

FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1
ENV TESSDATA_PREFIX=/usr/share/tesseract-ocr/4.00/tessdata

# -----------------------------
# 📦 نصب ابزارها و وابستگی‌ها
# -----------------------------
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    poppler-utils \
    supervisor \
    wget \
    libtesseract-dev \
    libgl1 \
    libglib2.0-0 \
    fonts-hosny-amiri \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# -----------------------------
# 📂 مسیر کاری و نصب کتابخانه‌های پایتون
# -----------------------------
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# -----------------------------
# ⚙️ پیکربندی Supervisor
# -----------------------------
RUN mkdir -p /var/log/supervisor
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# -----------------------------
# 📥 دانلود مدل‌های best هنگام اجرای کانتینر
# (نه در زمان build)
# -----------------------------
CMD bash -c "\
mkdir -p /usr/share/tesseract-ocr/4.00/tessdata && \
cd /usr/share/tesseract-ocr/4.00/tessdata && \
echo '📦 Downloading Tesseract best models...' && \
wget -q -O fas.traineddata https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/main/fas.traineddata || true && \
wget -q -O ara.traineddata https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/main/ara.traineddata || true && \
wget -q -O eng.traineddata https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/main/eng.traineddata || true && \
echo '✅ OCR traineddata files ready.' && \
/usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf"
