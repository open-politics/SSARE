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

# Install dependencies
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy custom File and Locks.
COPY rag_service /app/rag_service
COPY pyproject.toml /app/pyproject.toml
COPY poetry.lock /app/poetry.lock

# Install Python dependencies
RUN pip install --no-cache-dir -r /app/requirements.txt


# Copy the core directory
COPY core /app/core

# Run the server
CMD ["poetry", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "4312"]
