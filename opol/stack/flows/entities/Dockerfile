FROM python:3.11-slim AS base

WORKDIR /app

ENV UV_SYSTEM_PYTHON=1

RUN apt-get update && apt-get install -y git

RUN pip install uv

# Copy the requirements.txt file
COPY services/service-entities/requirements.txt .
RUN uv pip install --no-cache-dir -r requirements.txt

# Copy the core directory
COPY ../../core/ ./core

COPY flows/entities/ ./
