FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir .

COPY src ./src
COPY web ./web
COPY docs/recipes ./docs/recipes
COPY library ./library

ENV PORT=8000
EXPOSE 8000

# sh -c so ${PORT} injected by the platform is expanded
CMD ["sh", "-c", "uvicorn src.api.app:app --host 0.0.0.0 --port ${PORT}"]
