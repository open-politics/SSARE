FROM python:3.11-slim AS base

WORKDIR /app/

ENV UV_SYSTEM_PYTHON=1

# Set PYTHONPATH
ENV PYTHONPATH=/.

# Install dependencies
RUN apt-get update && \
    apt-get install -y netcat-traditional && \
    rm -rf /var/lib/apt/lists/*

RUN pip install uv

# Copy the requirements.txt file and install Python dependencies
COPY services/service-postgres/requirements.txt /app/
RUN uv pip install --no-cache-dir -r /app/requirements.txt

# Copy the service-postgres directory
COPY services/service-postgres .

# Copy the core directory
COPY ../../core/ ./core

# Copy the alembic directory
COPY services/service-postgres/alembic ./alembic
COPY services/service-postgres/start.sh .
RUN chmod +x start.sh

CMD ["./start.sh"]