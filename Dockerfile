# =======================================================
# 🧠 Dockerfile — OCR هوشمند با Flask برای UptimeRobot
# نسخه نهایی بدون خطای bot.py
# =======================================================

FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1
ENV TESSDATA_PREFIX=/usr/share/tesseract-ocr/4.00/tessdata

# 🧩 نصب ابزارها و پکیج‌های مورد نیاز سیستم
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    poppler-utils \
    wget \
    libtesseract-dev \
    libgl1 \
    libglib2.0-0 \
    fonts-hosny-amiri \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# 📂 تنظیم دایرکتوری کاری
WORKDIR /app

# 🧠 نصب پکیج‌های پایتون
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 📦 کپی کل فایل‌های پروژه به کانتینر
COPY . .

# 🌐 باز کردن پورت Flask برای UptimeRobot
EXPOSE 10000

# 🚀 دانلود مدل‌های OCR و اجرای بات در مسیر صحیح
CMD bash -c "\
mkdir -p /usr/share/tesseract-ocr/4.00/tessdata && \
cd /usr/share/tesseract-ocr/4.00/tessdata && \
echo '📦 Downloading OCR models (best & fast)...'; \
wget -q -O fas.traineddata https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/main/fas.traineddata || true; \
wget -q -O fas_fast.traineddata https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/fas.traineddata || true; \
wget -q -O eng.traineddata https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/main/eng.traineddata || true; \
echo '✅ OCR traineddata files ready.'; \
cd /app && python3 bot.py"
