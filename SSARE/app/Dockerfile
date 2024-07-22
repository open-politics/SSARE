FROM python:3.11


WORKDIR /app

COPY app/ .
COPY core/ ./core
COPY flows/ ./flows

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8089"] 