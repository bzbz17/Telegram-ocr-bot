FROM python:3.10-slim

ENV DEBIAN_FRONTEND=noninteractive

# نصب پکیج‌های لازم برای OpenCV و OCR
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    pkg-config \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    tesseract-ocr \
    tesseract-ocr-fas \
    tesseract-ocr-ara \
    tesseract-ocr-eng \
    libtesseract-dev \
    poppler-utils \
    ghostscript \
    wget \
    supervisor \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .

# نصب همه وابستگی‌ها از فایل requirements
RUN pip install --no-cache-dir -r requirements.txt

# کپی کل سورس پروژه
COPY . .

# پورت Flask
EXPOSE 8080

CMD ["python", "bot.py"]
