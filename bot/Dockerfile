FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/data

# LibreOffice — PDF formati uchun; shriftlar — PDF va dizaynlar rasmi (kollaj) chiroyli chiqishi uchun
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libreoffice-writer-nogui libreoffice-impress-nogui \
        fonts-dejavu fonts-liberation fonts-noto-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .

# Root'siz ishlaydi; baza va LibreOffice profili /data da (docker-compose diskka ulaydi)
RUN useradd --create-home bot && mkdir -p /data && chown bot:bot /data
USER bot
VOLUME /data

CMD ["python", "bot.py"]
