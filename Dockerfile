FROM python:3.13-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    flask \
    python-dotenv \
    pymongo \
    argon2-cffi \
    pyjwt \
    pika

COPY . .

RUN useradd --create-home --shell /bin/bash app && chown -R app:app /app
USER app

EXPOSE 5000

CMD ["python", "app.py"]
