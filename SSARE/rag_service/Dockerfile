FROM python:3.11

WORKDIR /app

# Set environment variables
ENV POSTGRES_USER=$POSTGRES_USER
ENV POSTGRES_PASSWORD=$POSTGRES_PASSWORD
ENV POSTGRES_HOST=$POSTGRES_HOST
ENV POSTGRES_PORT=$POSTGRES_PORT
ENV POSTGRES_DBNAME=$POSTGRES_DBNAME
ENV POSTGRES_VECS_COLLECTION=$POSTGRES_VECS_COLLECTION
ENV OPENAI_API_KEY=$OPENAI_API_KEY

# Install dependencies & poetry
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/* \
    && pip install poetry

# Copy custom File and Locks.
COPY core ./core
COPY rag_service/poetry.lock .
COPY rag_service/pyproject.toml .
COPY rag_service/requirements.txt .
COPY rag_service/main.py .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt
RUN poetry install

# Core Packages

# Clone and install R2R
RUN git clone https://github.com/SciPhi-AI/R2R.git \
    && cd R2R \
    && pip install . \
    && cd ..

# Run the server
CMD ["poetry", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "4312"]
