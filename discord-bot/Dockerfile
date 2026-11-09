# Imagem do Bot do Discord do SACIBot
# Build: docker build -t <usuario>/sacibot-discord-bot:latest ./discord-bot
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/requirements.txt

COPY . /app/

CMD ["python", "bot.py"]
