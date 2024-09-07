FROM ragtoriches/prod

WORKDIR /app

COPY rag_service/ .
COPY core/ ./bcore

RUN pip install -r requirements.txt

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "4312"]