FROM python:3.11-slim  # или ваш базовый образ
WORKDIR /opt/build

# Копируем файл зависимостей внутрь контейнера
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt
