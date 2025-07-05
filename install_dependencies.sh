#!/bin/bash

# Обновляем pip
python -m pip install --upgrade pip

# Устанавливаем зависимости
pip install -r requirements.txt

# Дополнительные системные зависимости (если нужны)
apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*
