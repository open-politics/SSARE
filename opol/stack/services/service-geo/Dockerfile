FROM python:3.11-slim

WORKDIR /app

ENV UV_SYSTEM_PYTHON=1

RUN apt-get update && apt-get install -y curl git

RUN pip install uv

# Copy the requirements.txt file
COPY services/service-geo/requirements.txt .
RUN uv pip install --no-cache-dir -r requirements.txt

# Copy the core directory
COPY ../../core/ ./core

# Copy the main.py and other files from service-postgres
COPY services/service-geo/main.py .
COPY services/service-geo/run_with_logfire.py .

COPY services/service-geo/start.sh .
RUN chmod +x start.sh

CMD ["./start.sh"]
