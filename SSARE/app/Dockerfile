FROM python:3.10


WORKDIR /app

# Copy only the requirements.txt file first
COPY app/ .
COPY core/ ./core
COPY flows/ ./flows

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8089"]