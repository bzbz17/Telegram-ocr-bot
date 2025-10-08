FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-fas \
    tesseract-ocr-eng \
    poppler-utils \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

ENV POPPLER_PATH=/usr/bin
ENV PYTHONUNBUFFERED=1

CMD ["python", "bot.py"]
