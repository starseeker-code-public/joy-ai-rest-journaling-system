FROM python:3.13-slim

WORKDIR /app

COPY . .

# Single source of truth for runtime deps: pyproject.toml
RUN pip install --no-cache-dir .

RUN useradd --create-home --shell /bin/bash app && chown -R app:app /app
USER app

EXPOSE 5000

CMD ["python", "app.py"]
