FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY prompts/ prompts/

EXPOSE 8000

# Env vars (OTO_PG_DSN, OTO_N8N_*) via UI do EasyPanel — nunca commitadas neste repo.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
