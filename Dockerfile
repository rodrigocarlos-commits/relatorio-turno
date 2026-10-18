FROM python:3.10-slim

# Instala dependências do sistema necessárias para o Playwright/Chromium
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    && rm -rf /var/lib/apt-lists/*

WORKDIR /app

# Instala as bibliotecas Python
RUN pip install --no-cache-dir flask gunicorn playwright

# Instala o navegador Chromium para renderizar o PDF
RUN playwright install --with-deps chromium

COPY . /app

EXPOSE 8080

CMD ["gunicorn", "-b", "0.0.0.0:8080", "app:app"]
