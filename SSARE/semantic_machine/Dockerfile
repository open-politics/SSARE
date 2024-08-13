FROM python:3.11-slim

WORKDIR /app

COPY semantic_machine/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY core ./core

COPY semantic_machine/main.py .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5688"]