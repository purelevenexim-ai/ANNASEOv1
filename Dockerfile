FROM python:3.12-slim AS builder
WORKDIR /app

# system deps
RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

FROM python:3.12-slim
WORKDIR /app

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY . ./

ENV ANNASEO_DB=/data/annaseo/annaseo.db
ENV ANNASEO_ENV=production
ENV PYTHONUNBUFFERED=1

VOLUME /data/annaseo

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
