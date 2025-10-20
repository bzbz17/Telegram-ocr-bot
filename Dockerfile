# ==========================
# Base Image
# ==========================
FROM python:3.10-slim

# ==========================
# Install System Dependencies
# ==========================
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    libtesseract-dev \
    libgl1 \
    poppler-utils \
    ghostscript \
    wget \
    supervisor \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ==========================
# Copy project files
# ==========================
WORKDIR /app
COPY . /app

# ==========================
# Install Python Dependencies
# ==========================
RUN pip install --upgrade pip setuptools wheel
RUN pip install --no-cache-dir \
    opencv-python-headless \
    pytesseract \
    pdf2image \
    PyMuPDF \
    flask \
    python-telegram-bot \
    hazm \
    numpy \
    pillow \
    easyocr

# ==========================
# OCR Language Data
# ==========================
RUN mkdir -p /usr/share/tesseract-ocr/4.00/tessdata && \
    wget -q -O /usr/share/tesseract-ocr/4.00/tessdata/fas.traineddata https://github.com/tesseract-ocr/tessdata_best/raw/main/fas.traineddata && \
    wget -q -O /usr/share/tesseract-ocr/4.00/tessdata/ara.traineddata https://github.com/tesseract-ocr/tessdata_best/raw/main/ara.traineddata && \
    wget -q -O /usr/share/tesseract-ocr/4.00/tessdata/eng.traineddata https://github.com/tesseract-ocr/tessdata_best/raw/main/eng.traineddata

# ==========================
# Supervisor Config
# ==========================
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# ==========================
# Expose Flask Port
# ==========================
EXPOSE 8080

# ==========================
# Run Supervisor (starts Flask + Bot)
# ==========================
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
