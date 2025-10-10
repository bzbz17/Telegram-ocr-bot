# =======================================================
# 🧠 Dockerfile — OCR فارسی/عربی/انگلیسی با مدل‌های BEST
# نسخه نهایی و تست‌شده برای Render و Railway
# =======================================================

FROM python:3.10-slim

# -----------------------------
# 🧩 تنظیمات پایه محیط
# -----------------------------
ENV PYTHONUNBUFFERED=1
ENV TESSDATA_PREFIX=/usr/share/tesseract-ocr/4.00/tessdata

# -----------------------------
# 📦 نصب وابستگی‌ها و ابزارها
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
# 📥 دانلود مدل‌های BEST (دقیق‌ترین نسخه)
# - شامل فارسی (fas)، عربی (ara) و انگلیسی (eng)
# - با کنترل خطا و mirror در صورت timeout
# -----------------------------
RUN set -eux; \
    cd /usr/share/tesseract-ocr/4.00/tessdata; \
    echo "🔽 Downloading Persian (fas) model..."; \
    wget -q --retry-connrefused --waitretry=3 --timeout=30 --tries=5 \
      -O fas.traineddata https://github.com/tesseract-ocr/tessdata_best/raw/main/fas.traineddata || \
    wget -q -O fas.traineddata https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/main/fas.traineddata; \
    echo "🔽 Downloading Arabic (ara) model..."; \
    wget -q --retry-connrefused --waitretry=3 --timeout=30 --tries=5 \
      -O ara.traineddata https://github.com/tesseract-ocr/tessdata_best/raw/main/ara.traineddata || \
    wget -q -O ara.traineddata https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/main/ara.traineddata; \
    echo "🔽 Downloading English (eng) model..."; \
    wget -q --retry-connrefused --waitretry=3 --timeout=30 --tries=5 \
      -O eng.traineddata https://github.com/tesseract-ocr/tessdata_best/raw/main/eng.traineddata || \
    wget -q -O eng.traineddata https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/main/eng.traineddata; \
    echo "✅ OCR traineddata files downloaded:"; \
    ls -lh /usr/share/tesseract-ocr/4.00/tessdata

# -----------------------------
# 📂 مسیر کاری و نصب پکیج‌های پایتون
# -----------------------------
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# -----------------------------
# 📁 کپی سورس پروژه
# -----------------------------
COPY . .

# -----------------------------
# ⚙️ تنظیم Supervisor برای اجرای دائمی ربات
# -----------------------------
RUN mkdir -p /var/log/supervisor
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# -----------------------------
# 🧪 تست اولیه مدل‌ها (اختیاری)
# اگر خواستی در لاگ Render ببینی مدل‌ها نصب شدن، این خط فعال باشه:
# -----------------------------
RUN tesseract --list-langs || true

# -----------------------------
# 🚀 اجرای نهایی
# -----------------------------
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
