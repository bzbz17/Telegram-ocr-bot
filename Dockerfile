# =============================================
# 🧠 Dockerfile — نسخه‌ی نهایی با مدل‌های Tesseract Best
# =============================================
FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1
ENV TESSDATA_PREFIX=/usr/share/tesseract-ocr/4.00/tessdata

# ----------------------------
# نصب ابزارهای OCR و وابستگی‌ها
# ----------------------------
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    poppler-utils \
    libtesseract-dev \
    libgl1 \
    libglib2.0-0 \
    supervisor \
    wget \
    fonts-dejavu-core \
    fonts-hosny-amiri \
    && rm -rf /var/lib/apt/lists/*

# ----------------------------
# 📥 دانلود مدل‌های BEST زبان‌ها (فارسی، عربی، انگلیسی)
# ----------------------------
RUN wget -O /usr/share/tesseract-ocr/4.00/tessdata/fas.traineddata https://github.com/tesseract-ocr/tessdata_best/raw/main/fas.traineddata \
 && wget -O /usr/share/tesseract-ocr/4.00/tessdata/ara.traineddata https://github.com/tesseract-ocr/tessdata_best/raw/main/ara.traineddata \
 && wget -O /usr/share/tesseract-ocr/4.00/tessdata/eng.traineddata https://github.com/tesseract-ocr/tessdata_best/raw/main/eng.traineddata

# ----------------------------
# نصب کتابخانه‌های پایتون
# ----------------------------
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ----------------------------
# کپی سورس پروژه
# ----------------------------
COPY . .

# ----------------------------
# اجرای خودکار با Supervisor
# ----------------------------
RUN mkdir -p /var/log/supervisor
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
