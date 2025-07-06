# Вихідний образ з Python
FROM python:3.10-slim

# Встановлюємо робочу директорію
WORKDIR /app

# Копіюємо залежності
COPY requirements.txt .

# Встановлюємо залежності
RUN pip install --no-cache-dir -r requirements.txt

# Копіюємо весь проєкт
COPY . .

# Експортуємо порт (Flask)
EXPOSE 5000

# Встановлюємо змінну середовища
ENV FLASK_APP=main.py

# Запуск
CMD ["flask", "run", "--host=0.0.0.0", "--port=5000"]