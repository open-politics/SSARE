FROM python:3.11-slim

WORKDIR /app

# Copy requirements file
COPY app/requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY app/ .
COPY core/ ./core
COPY flows/ ./flows

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8089"]