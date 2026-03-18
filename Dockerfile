FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# data dir will be mounted as a volume — create it so it exists in image too
RUN mkdir -p /app/data

CMD ["python", "bot.py"]
