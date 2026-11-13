FROM python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/backend
WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt && useradd --uid 10001 --create-home tradebot
COPY backend/postgres /app/backend/postgres
COPY docs/PLAN/INTELLIGENCE_REBUILD_PLAN.md /app/docs/PLAN/INTELLIGENCE_REBUILD_PLAN.md
USER 10001:10001
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "postgres.api:app", "--host", "0.0.0.0", "--port", "8000"]
