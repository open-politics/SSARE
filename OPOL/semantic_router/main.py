import os
import json
import logging
from typing import List, Optional, Dict
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
import textgrad as tg
from core.adb import get_session
from core.models import Article, Tag, ArticleTag
import httpx
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from collections import defaultdict
from groq import Groq
import instructor
from datetime import datetime

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI()

# Initialize TextGrad
tg.set_backward_engine("gpt-4")

# Initialize Groq client
client = instructor.from_groq(Groq(api_key=os.getenv("GROQ_API_KEY")))

# Define the NewsArticleClassification model (as in your script)
class NewsArticleClassification(BaseModel):
    
    pass

# Initialize RouteLayer (we'll populate this later)
encoder = tg.OpenAIEncoder()
routes = []
route_layer = None

async def generate_gold_standard_articles(num_articles: int = 100) -> List[NewsArticleClassification]:
    articles = []
    # modify: pull random articles from db
    for _ in range(num_articles):
        prompt = f"Generate a complex political news article about a fictional global event."
        article = await client.chat.completions.acreate(
            model="llama-3.1-8b-instant",
            response_model=str,
            messages=[{"role": "user", "content": prompt}],
        )
        classification = await client.chat.completions.acreate(
            model="llama-3.1-8b-instant",
            response_model=NewsArticleClassification,
            messages=[
                {"role": "user", "content": f"Analyze this complex political news article in great detail: {article}"},
            ],
        )
        articles.append(classification)
    return articles

async def infer_optimal_routes(gold_standard_articles: List[NewsArticleClassification]) -> List[tg.Route]:
    # Aggregate categories and keywords
    categories = defaultdict(int)
    keywords = defaultdict(int)
    for article in gold_standard_articles:
        categories[article.primary_category] += 1
        for category in article.secondary_categories:
            categories[category] += 1
        for keyword in article.keywords:
            keywords[keyword] += 1
    
    # Select top categories and keywords
    top_categories = sorted(categories.items(), key=lambda x: x[1], reverse=True)[:10]
    top_keywords = sorted(keywords.items(), key=lambda x: x[1], reverse=True)[:50]
    
    # Generate routes
    routes = []
    for category, _ in top_categories:
        related_keywords = [kw for kw, _ in top_keywords if any(kw.lower() in article.keywords for article in gold_standard_articles if article.primary_category == category)][:5]
        route = tg.Route(
            name=category,
            utterances=[category] + related_keywords
        )
        routes.append(route)
    
    return routes

@app.post("/generate_gold_standard")
async def generate_gold_standard(num_articles: int = 100):
    articles = await generate_gold_standard_articles(num_articles)
    global routes
    routes = await infer_optimal_routes(articles)
    global route_layer
    route_layer = tg.RouteLayer(encoder=encoder, routes=routes)
    return {"message": f"Generated {num_articles} gold standard articles and inferred {len(routes)} routes"}

async def get_embeddings(texts: List[str]) -> List[List[float]]:
    async with httpx.AsyncClient() as client:
        embeddings = []
        for text in texts:
            response = await client.get("http://embedding-service:8000/generate_query_embeddings", params={"query": text})
            response.raise_for_status()
            embeddings.append(response.json()["embeddings"])
        return embeddings

def coherence_score(embeddings: List[List[float]]) -> float:
    similarity_matrix = cosine_similarity(embeddings)
    return np.mean(similarity_matrix)

def inter_route_distance(route_embeddings: List[List[float]]) -> float:
    similarity_matrix = cosine_similarity(route_embeddings)
    np.fill_diagonal(similarity_matrix, 0)  # Exclude self-similarity
    return 1 - np.mean(similarity_matrix)  # Return distance instead of similarity

async def coverage_analysis(session: AsyncSession, sample_size: int = 100) -> float:
    # Sample articles from the database
    stmt = select(Article).order_by(func.random()).limit(sample_size)
    result = await session.execute(stmt)
    articles = result.scalars().all()

    # Get embeddings for article headlines
    article_embeddings = await get_embeddings([article.headline for article in articles])

    # Get embeddings for route utterances
    route_embeddings = await get_embeddings([" ".join(route.utterances) for route in routes])

    # Calculate coverage
    covered_articles = 0
    for article_embedding in article_embeddings:
        similarities = cosine_similarity([article_embedding], route_embeddings)[0]
        if np.max(similarities) > 0.5:  # Threshold for considering an article covered
            covered_articles += 1

    return covered_articles / sample_size

@app.post("/optimize_routes")
async def optimize_routes(background_tasks: BackgroundTasks, session: AsyncSession = Depends(get_session)):
    async def optimize():
        system_prompt = tg.Variable(
            "You are an AI assistant optimizing semantic routes for article classification.",
            requires_grad=True,
        )
        model = tg.BlackboxLLM("gpt-4", system_prompt=system_prompt)
        optimizer = tg.TGD(parameters=list(model.parameters()))

        for route in routes:
            route.utterances = tg.Variable(route.utterances, requires_grad=True)
            optimizer.add_param_group({"params": [route.utterances]})

        # Optimization loop
        for _ in range(5):  # Adjust the number of optimization steps as needed
            # Collect metrics
            route_embeddings = await get_embeddings([" ".join(route.utterances) for route in routes])
            coherence_scores = [coherence_score(await get_embeddings(route.utterances)) for route in routes]
            route_distance = inter_route_distance(route_embeddings)
            coverage = await coverage_analysis(session)

            # Use metrics in the optimization process
            for i, route in enumerate(routes):
                metrics_prompt = f"""
                Optimize the '{route.name}' route based on the following metrics:
                - Coherence score: {coherence_scores[i]:.2f}
                - Inter-route distance: {route_distance:.2f}
                - Coverage: {coverage:.2f}
                
                Current utterances: {route.utterances}
                
                Suggest improvements to increase coherence while maintaining distinctiveness from other routes and improving overall coverage.
                """
                prediction = model(metrics_prompt)
                loss = tg.TextLoss("Evaluate the suggestions for improving the route based on the given metrics")(prediction)
                loss.backward()
                optimizer.step()
                optimizer.zero_grad()

        # Update routes with optimized utterances
        for route in routes:
            route.utterances = route.utterances.value

        # Reinitialize RouteLayer with optimized routes
        global route_layer
        route_layer = tg.RouteLayer(encoder=encoder, routes=routes)

    background_tasks.add_task(optimize)
    return {"message": "Route optimization started in the background"}

@app.post("/semantic_search")
async def semantic_search(query: str, session: AsyncSession = Depends(get_session)):
    try:
        # Route the query
        route_choice = route_layer(query)
        
        # Perform vector search (assuming you have a vector_search function)
        articles = await vector_search(query, session)
        
        # Tag articles based on the route
        for article in articles:
            await tag_article(article, route_choice.name, session)
        
        return {
            "route": route_choice.name,
            "articles": [
                {
                    "id": str(article.id),
                    "url": article.url,
                    "headline": article.headline,
                    "tags": [tag.name for tag in article.tags]
                }
                for article in articles
            ]
        }
    except Exception as e:
        logger.error(f"Error in semantic search: {e}")
        raise HTTPException(status_code=500, detail="Error performing semantic search")

@app.get("/route_metrics")
async def get_route_metrics(session: AsyncSession = Depends(get_session)):
    try:
        route_embeddings = await get_embeddings([" ".join(route.utterances) for route in routes])
        coherence_scores = [coherence_score(await get_embeddings(route.utterances)) for route in routes]
        route_distance = inter_route_distance(route_embeddings)
        coverage = await coverage_analysis(session)

        return {
            "coherence_scores": {route.name: score for route, score in zip(routes, coherence_scores)},
            "inter_route_distance": route_distance,
            "coverage": coverage
        }
    except Exception as e:
        logger.error(f"Error calculating route metrics: {e}")
        raise HTTPException(status_code=500, detail="Error calculating route metrics")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)