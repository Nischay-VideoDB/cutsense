FROM python:3.12-slim

WORKDIR /app

# Dependencies first so code edits don't invalidate the install layer.
# The app runs from the working directory (uvicorn src.api.app:app), so the
# package itself is never installed — installing it would require src/ to exist
# in this layer and would rebuild on every code change.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY web ./web
COPY docs/recipes ./docs/recipes
COPY library ./library

ENV PORT=8000 PYTHONUNBUFFERED=1
EXPOSE 8000

# sh -c so ${PORT} injected by the platform is expanded
CMD ["sh", "-c", "uvicorn src.api.app:app --host 0.0.0.0 --port ${PORT}"]
