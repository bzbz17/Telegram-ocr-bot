FROM python:3.10-slim

# جلوگیری از پرسش‌های نصب
ENV DEBIAN_FRONTEND=noninteractive

# نصب پکیج‌ها و Tesseract
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-fas \
    tesseract-ocr-ara \
    tesseract-ocr-eng \
    libgl1 \
    poppler-utils \
    ghostscript \
    wget \
    supervisor && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# کپی فایل‌ها
WORKDIR /app
COPY . .

# نصب پکیج‌های پایتون
RUN pip install --no-cache-dir -r requirements.txt

# Supervisor config
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

CMD ["supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
