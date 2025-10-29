# ---------- مرحله ۱: ایمیج پایه ----------
FROM python:3.10-slim

# ---------- مرحله ۲: تنظیم محیط ----------
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV TESSDATA_PREFIX=/usr/share/tesseract-ocr/4.00/tessdata

# ---------- مرحله ۳: نصب وابستگی‌های سیستم ----------
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-fas \
    tesseract-ocr-eng \
    poppler-utils \
    ghostscript \
    libtesseract-dev \
    libgl1 \
    libglib2.0-0 \
    fonts-dejavu \
    fonts-freefont-ttf \
    fonts-hosny-amiri \
    fonts-noto-cjk \
    fonts-noto-unhinted \
    fonts-dejavu-core \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ---------- مرحله ۴: مسیر کاری ----------
WORKDIR /app

# ---------- مرحله ۵: نصب پکیج‌های پایتون ----------
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# ---------- مرحله ۶: کپی سورس کد ----------
COPY . .

# ---------- مرحله ۷: تنظیم محیط برای سرعت بالاتر OCR ----------
# PSM 6 برای تشخیص خطوط معمولی، OEM 3 برای حالت ترکیبی بهترین کیفیت
ENV TESSERACT_OEM=3
ENV TESSERACT_PSM=6
ENV OCR_THREADS=4

# ---------- مرحله ۸: اجرای ربات ----------
CMD ["python", "bot.py"]
