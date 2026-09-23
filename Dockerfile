FROM python:3.11-slim

WORKDIR /app

COPY main.py .

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir \
    yandex-music \
    requests \
    mutagen \
    tqdm

CMD ["python", "-u", "main.py", "--sync"]