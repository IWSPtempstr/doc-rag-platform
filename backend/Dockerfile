FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./alembic.ini

ENV DATABASE_URL=sqlite:///./storage/app.db
ENV REDIS_URL=redis://redis:6379/0
ENV CHAT_PROVIDER=openai
ENV EMBEDDING_PROVIDER=ollama
ENV CHAT_MODEL=deepseek-v4-flash
ENV EMBEDDING_MODEL=nomic-embed-text
ENV OLLAMA_BASE_URL=http://ollama:11434
ENV STORAGE_DIR=storage

RUN mkdir -p storage/uploads storage/chroma storage/traces storage/evaluations storage/assets

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
