FROM python:3.9-slim

WORKDIR /app

# Копируем зависимости отдельно для кэширования
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем остальной код
COPY . .

# Команда запуска бота
CMD ["python", "main.py"]
