from typing import List
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel, select
from fastapi import FastAPI, HTTPException, Depends
from core.utils import load_config 
from core.models import ArticleBase, ArticlePydantic
import os
from fastapi import APIRouter
from r2r import R2RAppBuilder, Document
import json

app = FastAPI()

# Load configuration
config = load_config()['postgresql']

# Database setup
DATABASE_URL = f"postgresql+asyncpg://{config['postgres_user']}:{config['postgres_password']}@{config['postgres_host']}/{config['postgres_db']}"
engine = create_async_engine(DATABASE_URL)
if os.getenv("INITDB") == "True":
    print("Initializing database")
    SQLModel.metadata.create_all(engine)

# Dependency to get DB session
async def get_db():
    async with AsyncSession(engine) as session:
        yield session

@app.get("/healthz")
async def healthcheck():
    return {"message": "RAG Service Running"}, 200

@app.get("/articles/", response_model=List[ArticlePydantic])
async def read_articles(skip: int = 0, limit: int = 10, db: AsyncSession = Depends(get_db)):
    statement = select(ArticleBase).offset(skip).limit(limit)
    result = await db.execute(statement)
    db_articles = result.scalars().all()
    return db_articles

async def get_articles(skip: int = 0, limit: int = 10, db: AsyncSession = Depends(get_db)):
    statement = select(ArticleBase).offset(skip).limit(limit)
    result = await db.execute(statement)
    db_articles = result.scalars().all()
    return db_articles

async def process_documents():
    r2r_app = R2RAppBuilder(from_config="neo4j_kg").build()

    ## ToDo: Pull articles from Postgres // which rule? // --> topics

    ## Metadata is optional, but filtered locations, entities and other classifications need be inserted
    try:
        with open('response.json', 'r') as f:
            response = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")
        return

    # Transform the documents into a list of Document objects
    documents = []
    for result in response["results"]:
        entities = [{"text": entity["text"], "tag": entity["tag"]} for entity in result.get("entities", [])]
        documents.append(
            Document(
                type="txt",
                data=result["content"],
                metadata={
                    "title": result["title"],
                    "url": result["url"],
                    "published_date": result["published date"],
                    "score": result["score"],
                    "entities": entities,
                    "locations": [entity["text"] for entity in result.get("entities", []) if entity["tag"] == "GPE"],
                    "organizations": [entity["text"] for entity in result.get("entities", []) if entity["tag"] == "ORG"],
                    "persons": [entity["text"] for entity in result.get("entities", []) if entity["tag"] == "PERSON"],
                    "dates": [entity["text"] for entity in result.get("entities", []) if entity["tag"] == "DATE"],
                },
            )
        )
    
    for doc in documents:
        print(f"Title: {doc.metadata['title']}")
        print(f"URL: {doc.metadata['url']}")
        print(f"Published Date: {doc.metadata['published_date']}")
        print(f"Score: {doc.metadata['score']}")
        print("Entities:")
        for entity in doc.metadata['entities']:
            print(f"  - {entity['text']} ({entity['tag']})")
        print("Locations:", ", ".join(doc.metadata['locations']))
        print("Organizations:", ", ".join(doc.metadata['organizations']))
        print("Persons:", ", ".join(doc.metadata['persons']))
        print("Dates:", ", ".join(doc.metadata['dates']))
        print("Content:", str(doc.data)[:200] + "..." if len(doc.data) > 200 else doc.data)
        print("\n" + "-"*80 + "\n")

    print('hi')
    print('ho')

@app.get("/process")
async def process():
    await process_documents()
    print("Processing documents")
    return {"message": "Processing documents"}, 200