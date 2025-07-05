FROM python:3.9-slim
COPY . /app
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "main.py"]
ENTRYPOINT ["python"]
EXPOSE 3478
