from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
import logging

async def retrieve_similar_entities(entity_name: str, session: AsyncSession):
    try:
        # Use plainto_tsquery for better handling of spaces and special characters
        tsquery = func.plainto_tsquery(entity_name)
        
        # Construct the query
        similar_entities_stmt = select(entity.id, entity.name, entity.entity_type).where(
            entity.entity_type == 'LOC',
            entity.id != some_uuid,
            entity.name.op('@@')(tsquery),
            func.similarity(entity.name, entity_name) > 0.3
        ).limit(5)
        
        # Execute the query
        result = await session.execute(similar_entities_stmt)
        return result.fetchall()
    
    except SQLAlchemyError as e:
        logging.error(f"Database error: {e}")
        raise

# Example usage in your main function
async def process_entity(entity):
    async with AsyncSession() as session:
        similar_entities = await retrieve_similar_entities(entity.name, session)
        # Process similar_entities as needed