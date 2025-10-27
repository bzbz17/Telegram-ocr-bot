FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-fas \
    tesseract-ocr-ara \
    libgl1 \
    poppler-utils \
    ghostscript \
    wget \
    supervisor \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --upgrade pip setuptools wheel \
 && pip install --no-cache-dir -r requirements.txt \
 && python -m nltk.downloader punkt

COPY . .

EXPOSE 8080

CMD ["supervisord", "-c", "/app/supervisord.conf"]
