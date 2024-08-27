from typing import Dict, Any, List
from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from core.models import Article, DynamicClassification
import json

class AlgoQuan:
    def __init__(self):
        self.dimension_weights = {}
        self.dimension_ranges = {}

    def set_dimension_weight(self, dimension: str, weight: float):
        self.dimension_weights[dimension] = weight

    def set_dimension_range(self, dimension: str, min_value: float, max_value: float):
        self.dimension_ranges[dimension] = (min_value, max_value)

    async def retrieve_articles(self, session: AsyncSession, schema_name: str, limit: int = 10) -> List[Article]:
        query = select(Article).join(DynamicClassification).where(DynamicClassification.schema_id == schema_name)

        for dimension, (min_value, max_value) in self.dimension_ranges.items():
            query = query.where(and_(
                func.cast(DynamicClassification.classification_data[dimension], float) >= min_value,
                func.cast(DynamicClassification.classification_data[dimension], float) <= max_value
            ))

        # Add ordering based on weighted dimensions
        order_clause = sum(
            self.dimension_weights.get(dim, 1) * func.cast(DynamicClassification.classification_data[dim], float)
            for dim in self.dimension_weights
        )
        query = query.order_by(order_clause.desc())

        query = query.options(selectinload(Article.classification))
        query = query.limit(limit)

        result = await session.execute(query)
        return result.scalars().unique().all()

algoquan = AlgoQuan()