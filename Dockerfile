# =======================================================
# 🐳 Dockerfile — OCR Bot فارسی / عربی / انگلیسی
# =======================================================

FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1
ENV TESSDATA_PREFIX=/usr/share/tesseract-ocr/4.00/tessdata

RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    poppler-utils \
    ghostscript \
    libtesseract-dev \
    libgl1 \
    libglib2.0-0 \
    fonts-hosny-amiri \
    fonts-dejavu-core \
    wget \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

EXPOSE 10000

CMD bash -c "\
mkdir -p /usr/share/tesseract-ocr/4.00/tessdata && \
cd /usr/share/tesseract-ocr/4.00/tessdata && \
echo '📦 Downloading OCR language models...'; \
wget -q -O fas.traineddata https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/main/fas.traineddata || true; \
wget -q -O ara.traineddata https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/main/ara.traineddata || true; \
wget -q -O eng.traineddata https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/main/eng.traineddata || true; \
echo '✅ OCR traineddata files ready.'; \
cd /app && python3 bot.py"
