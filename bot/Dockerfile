FROM python:3.11-slim

WORKDIR /app

# Установка зависимостей
RUN pip install --no-cache-dir python-telegram-bot requests

# Копирование бота
COPY bot.py /app/bot.py

# Создание директории для конфига
RUN mkdir -p /app/config

CMD ["python", "bot.py"]
