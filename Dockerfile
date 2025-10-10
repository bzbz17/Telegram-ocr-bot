FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1
ENV TESSDATA_PREFIX=/usr/share/tesseract-ocr/4.00/tessdata

RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-fas \
    tesseract-ocr-eng \
    poppler-utils \
    ghostscript \
    supervisor \
    libtesseract-dev \
    libgl1 \
    libglib2.0-0 \
    fonts-hosny-amiri \
    fonts-dejavu-core \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["/usr/bin/supervisord", "-c", "/app/supervisord.conf"]
