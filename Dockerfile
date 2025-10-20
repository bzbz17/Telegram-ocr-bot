FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-fas \
    tesseract-ocr-eng \
    tesseract-ocr-ara \
    libgl1 poppler-utils ghostscript supervisor wget \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["/usr/bin/supervisord", "-c", "/app/supervisord.conf"]
