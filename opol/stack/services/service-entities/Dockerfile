FROM python:3.11-slim

WORKDIR /app

ENV UV_SYSTEM_PYTHON=1

RUN apt-get update && apt-get install -y curl git

RUN pip install uv

# Copy the requirements.txt file
COPY services/service-entities/requirements.txt .
RUN uv pip install --no-cache-dir -r requirements.txt

# Copy the core directory
COPY ../../core/ ./core

COPY services/service-entities/main.py .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "1290"]
