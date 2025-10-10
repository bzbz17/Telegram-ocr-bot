# ===============================
# 🔹 مرحله ۱: ایمیج پایه
# ===============================
FROM python:3.10-slim

# ===============================
# 🔹 مرحله ۲: تنظیمات عمومی محیط
# ===============================
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV TESSDATA_PREFIX=/usr/share/tesseract-ocr/4.00/tessdata

# ===============================
# 🔹 مرحله ۳: نصب ابزارهای OCR و وابستگی‌ها
# ===============================
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-fas \
    tesseract-ocr-eng \
    tesseract-ocr-ara \
    poppler-utils \
    libtesseract-dev \
    libgl1 \
    libglib2.0-0 \
    supervisor \
    fonts-dejavu \
    fonts-freefont-ttf \
    fonts-hosny-amiri \
    fonts-noto-cjk \
    fonts-noto-unhinted \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ===============================
# 🔹 مرحله ۴: مسیر کاری و نصب وابستگی‌های پایتون
# ===============================
WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# ===============================
# 🔹 مرحله ۵: کپی سورس پروژه
# ===============================
COPY . .

# ===============================
# 🔹 مرحله ۶: تنظیم Supervisord برای مدیریت اجرا و ری‌استارت خودکار
# ===============================
RUN mkdir -p /var/log/supervisor
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# ===============================
# 🔹 مرحله ۷: اجرای نهایی ربات
# ===============================
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
