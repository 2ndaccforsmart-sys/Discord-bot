FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=utf-8

RUN apt-get update && apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
        libnss3 libatk-bridge2.0-0 libdrm2 libxcomposite1 libxdamage1 \
        libxrandr2 libgbm1 libasound2 libpango-1.0-0 libcairo2 libatspi2.0-0 \
        libgtk-3-0 libxshmfence1 && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install --with-deps chromium

COPY bot.py .
COPY utils/ utils/
COPY cogs/ cogs/
COPY .env.example .

EXPOSE 7860
CMD ["python", "bot.py"]
