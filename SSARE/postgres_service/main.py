from pydantic import BaseModel
from typing import List, Dict
from fastapi import FastAPI
import requests
from core.utils import load_config
from sqlalchemy import create_engine
from sqlalchemy import inspect
from core.utils import load_config

config = load_config()['postgresql']

app = FastAPI()

class Article(BaseModel):
    url: str
    headline: str
    paragraphs: List[str]



@app.get("/flags")
def produce_flags():
    # Call the scraper service to get data
    # check if postgres entries have been older than 24 hours
    # if yes, return the flags
    return {"flags": ["cnn", "zdf", "fox"]}
    
@app.get('/receive_raw_articles')
def save_raw_articles(data):
    import pandas as pd
    from sqlalchemy.orm import sessionmaker

    # save articles to postgres
    database_name = load_config()['postgresql']['postgres_db']
    table_name = load_config()['postgresql']['postgres_table_name']
    user = load_config()['postgresql']['postgres_user']
    password = load_config()['postgresql']['postgres_password']
    host = load_config()['postgresql']['postgres_host']
    engine = create_engine(f'postgresql://{user}:{password}@{host}:5432/{database_name}')
    Session = sessionmaker(bind=engine)
    session = Session()

    data = data['data']['unprocessed_articles']
    articles = []

    for article_data in data:
        article = Article(url=article_data['url'], headline=article_data['headline'], paragraphs=article_data['paragraphs'])
        articles.append(article)

    
    session.add_all(articles)
    session.commit()

    return {"message": "Articles saved successfully"}


# add query endpoint
@app.get("/query_raw_articles")
def query_data(query):
    # query the postgres database
    # return the result
    pass

@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "ok"}


