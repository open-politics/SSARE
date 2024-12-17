import os
import json
import logging
import asyncio
from typing import List, Dict, Optional
import uuid
from datetime import datetime
import httpx
import time
from sqlmodel import select, SQLModel, Field, create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import func
from rich.console import Console
from rich.table import Table
from pydantic import BaseModel
from prometheus_client import start_http_server, Counter, Gauge
from core.service_mapping import ServiceConfig

config = ServiceConfig()

# ---------------------------
# Define Prometheus Metrics
# ---------------------------

resolution_counter = Counter(
    'entity_resolutions_total',
    'Total number of entity resolutions',
    ['action', 'entity_type']
)

resolution_gauge = Gauge(
    'entity_resolution_time_seconds',
    'Time taken to resolve an entity',
    ['entity_type']
)

similarity_gauge = Gauge(
    'entity_similarity_score',
    'Similarity score between entities',
    ['entity_id', 'similar_entity_id']
)

# ---------------------------
# Pydantic Models (Optional)
# ---------------------------

class ResolutionMetric(BaseModel):
    entity_id: uuid.UUID
    action: str
    new_name: Optional[str]
    resolved_at: datetime
    similarity_score: Optional[float] = None

# ---------------------------
# SQLModel Definitions
# ---------------------------

from core.models import Entity, Content, ContentEntity

# ---------------------------
# Database Setup
# ---------------------------

from core.service_mapping import get_db_url
DATABASE_URL = get_db_url()
engine = create_async_engine(DATABASE_URL, echo=False)

# ---------------------------
# Rich Console Setup
# ---------------------------

console = Console(force_terminal=True)

# ---------------------------
# In-Memory Storage
# ---------------------------

resolutions_storage: Dict[uuid.UUID, List[Dict]] = {}

# ---------------------------
# Helper Functions
# ---------------------------

async def retrieve_entities(entity_type: str, batch_size: int = 5, offset: int = 0) -> List[Entity]:
    async with AsyncSession(engine) as session:
        stmt = select(Entity).where(
            Entity.entity_type == entity_type
        ).options(selectinload(Entity.contents)).limit(batch_size).offset(offset)
        result = await session.execute(stmt)
        entities = result.scalars().all()

    table = Table(title=f"Retrieved Entities of type '{entity_type}'")
    table.add_column("Entity ID", style="cyan", no_wrap=True)
    table.add_column("Entity Name", style="magenta")
    table.add_column("Content Count", style="green")

    for entity in entities:
        table.add_row(str(entity.id), entity.name, str(len(entity.contents)))

    console.print(table)
    return entities

async def retrieve_similar_entities(entity: Entity, session: AsyncSession) -> List[Entity]:
    tsquery = func.plainto_tsquery(entity.name)

    similar_entities_stmt = select(Entity).where(
        Entity.entity_type == entity.entity_type,
        Entity.id != entity.id,
        Entity.name.op('@@')(tsquery),
        func.similarity(Entity.name, entity.name) > 0.3
    ).options(selectinload(Entity.contents)).limit(5)
    
    result = await session.execute(similar_entities_stmt)
    similar_entities = result.scalars().all()

    table = Table(title=f"Similar Entities for '{entity.name}'")
    table.add_column("Entity ID", style="cyan", no_wrap=True)
    table.add_column("Entity Name", style="magenta")
    table.add_column("Similarity Score", style="green")

    for sim_entity in similar_entities:
        similarity_score = await session.scalar(func.similarity(Entity.name, entity.name))
        table.add_row(str(sim_entity.id), sim_entity.name, f"{similarity_score:.2f}")
        similarity_gauge.labels(entity_id=str(entity.id), similar_entity_id=str(sim_entity.id)).set(similarity_score)

    console.print(table)
    return similar_entities

async def process_entity(entity: Entity):
    entity_name = entity.name
    entity_type = entity.entity_type
    console.print(f"[bold yellow]Processing entity '{entity_name}' of type '{entity_type}':[/bold yellow]")

    start_time = time.time()

    await asyncio.sleep(1)

    async with AsyncSession(engine) as session:
        stmt = select(Content).join(ContentEntity).where(ContentEntity.entity_id == entity.id).limit(3)
        result = await session.execute(stmt)
        contents = result.scalars().all()

    passages = []
    for content in contents:
        text = content.text_content
        if not text:
            console.print(f"[red]Warning:[/red] No text content found for entity '{entity_name}'.")
            continue
        idx = text.lower().find(entity_name.lower())
        if idx != -1:
            start = max(0, idx - 100)
            end = min(len(text), idx + 100)
            passage = text[start:end]
            passages.append(passage)
        else:
            passages.append(text[:200])

    await asyncio.sleep(1)

    async with AsyncSession(engine) as session:
        similar_entities = await retrieve_similar_entities(entity, session)

    similar_entity_names = [sim_entity.name for sim_entity in similar_entities]

    if not similar_entities:
        console.print(f"[blue]Info:[/blue] No similar entities found for '{entity_name}'.")
        action = 'none'
        new_name = None
    else:
        dimensions = [
            {
                'name': 'action',
                'type': 'string',
                'description': 'Decide whether to "merge", "modify", or "separate" the entities.'
            },
            {
                'name': 'new_name',
                'type': 'string',
                'description': 'If action is "merge" or "modify", provide the new unified name for the entities.'
            }
        ]

        payload = {
            "dimensions": dimensions,
            "entity_name": entity_name,
            "entity_type": entity_type,
            "passages": passages,
            "similar_entities": similar_entity_names
        }

        await asyncio.sleep(1)

        async with httpx.AsyncClient() as client:
            try:
                console.print(f"[green]Calling classification service for entity '{entity_name}'...[/green]")
                response = await client.post(f"{config.service_urls['classification-service']}/classify", json=payload, timeout=60)
                response.raise_for_status()
                classification_result = response.json()
                console.print(f"[blue]Debug:[/blue] Classification result: {classification_result}")
            except Exception as e:
                console.print(f"[red]Error:[/red] Calling classification service for '{entity_name}': {e}")
                action = 'error'
                new_name = None
                classification_result = {}
                resolution_counter.labels(action=action, entity_type=entity_type).inc()
                resolution_gauge.labels(entity_type=entity_type).set(time.time() - start_time)
                return

        table = Table(title=f"Classification Result for '{entity_name}'")
        table.add_column("Action", style="cyan")
        table.add_column("New Name", style="magenta")

        action = classification_result.get('action', '').lower()
        new_name = classification_result.get('new_name', None)
        table.add_row(action, new_name if new_name else "N/A")

        console.print(table)

    resolution_time = time.time() - start_time
    resolution_gauge.labels(entity_type=entity_type).set(resolution_time)
    resolution_counter.labels(action=action, entity_type=entity_type).inc()

    if entity.id not in resolutions_storage:
        resolutions_storage[entity.id] = []
    resolutions_storage[entity.id].append({
        'action': action,
        'new_name': new_name,
        'resolved_at': datetime.utcnow().isoformat()
    })

    async with AsyncSession(engine) as session:
        if action == 'merge':
            unified_name = new_name if new_name else entity_name
            console.print(f"[green]Merging entities into '{unified_name}'...[/green]")
            entity.name = unified_name
            await session.merge(entity)
            for sim_entity in similar_entities:
                sim_entity.name = unified_name
                await session.merge(sim_entity)
            await session.commit()
            console.print(f"[green]Entities merged successfully into '{unified_name}'.[/green]")
        elif action == 'modify':
            updated_name = new_name if new_name else entity_name
            console.print(f"[green]Modifying entity name to '{updated_name}' for '{entity_name}'...[/green]")
            entity.name = updated_name
            session.merge(entity)
            await session.commit()
            console.print(f"[green]Entity '{entity_name}' modified successfully to '{updated_name}'.[/green]")
        elif action == 'separate':
            console.print(f"[blue]Info:[/blue] No action taken for '{entity_name}' (separate).")
        elif action == 'error':
            console.print(f"[red]Error:[/red] An error occurred while processing '{entity_name}'.")
        else:
            console.print(f"[red]Warning:[/red] Unrecognized action '{action}' for entity '{entity_name}'.")

    console.print(f"[bold green]Entity '{entity_name}' processed with action '{action}'.[/bold green]")

async def resolve_entities_flow(entity_types: Optional[List[str]] = None):
    console.print("[bold cyan]Starting entity resolution process.[/bold cyan]")
    if entity_types is None:
        entity_types = ['LOC']

    for entity_type in entity_types:
        offset = 0
        batch_size = 1
        entities = await retrieve_entities(entity_type=entity_type, batch_size=batch_size, offset=offset)
        if not entities:
            console.print(f"[blue]Info:[/blue] No '{entity_type}' entities to process.")
            break
        for entity in entities:
            await process_entity(entity)
            await asyncio.sleep(1)
        await asyncio.sleep(2)
    console.print("[bold cyan]Entity resolution process completed.[/bold cyan]")

from prefect import flow

@flow(name="Entity Resolution Flow")
async def entity_resolution_prefect_flow(entity_types: Optional[List[str]] = None):
    await resolve_entities_flow(entity_types=entity_types)

if __name__ == "__main__":
    import os
    import asyncio
    from multiprocessing import Process

    def start_metrics_server():
        start_http_server(7451)
        logging.info("Prometheus metrics server started on port 7451.")

    def start_metrics():
        start_metrics_server()

    metrics_process = Process(target=start_metrics, daemon=True)
    metrics_process.start()
    logging.info("[INFO] Prometheus metrics server started on port 7451.")

    try:
        entity_types_to_resolve = ['LOC', 'ORG']

        logging.info("[INFO] Starting entity resolution process.")
        asyncio.run(entity_resolution_prefect_flow(entity_types=entity_types_to_resolve))
        logging.info("[INFO] Entity resolution process completed successfully.")

    except Exception as e:
        logging.error(f"[ERROR] An error occurred during entity resolution: {e}")

    finally:
        metrics_process.terminate()
        metrics_process.join()
        logging.info("[INFO] Prometheus metrics server terminated.")