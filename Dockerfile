FROM python:3.10-slim

WORKDIR /app

# نصب وابستگی‌های سیستمی
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libgl1 \
    poppler-utils \
    ghostscript \
    wget \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# نصب پکیج‌های پایتون
COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# کپی سورس
COPY . .

# پورت برای Flask
EXPOSE 8080

# اجرای برنامه
CMD ["python", "bot.py"]
