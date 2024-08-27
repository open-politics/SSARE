from typing import Dict, Any, List
from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from core.models import Article, DynamicClassification
import json
import openai

# Configure LiteLLM
my_proxy_api_key = "sk-1234"
my_proxy_base_url = "http://litellm:4000"


if os.getenv("LOCAL_LLM") == "True":
    client = instructor.from_openai(OpenAI(base_url=my_proxy_base_url, api_key=my_proxy_api_key))
else:
    client = instructor.from_openai(OpenAI(api_key=os.getenv("OPENAI_API_KEY")))


class AlgoQuan:
    def __init__(self):
        self.dimension_weights = {}
        self.dimension_ranges = {}

    def set_dimension_weight(self, dimension: str, weight: float):
        self.dimension_weights[dimension] = weight

    def set_dimension_range(self, dimension: str, min_value: float, max_value: float):
        self.dimension_ranges[dimension] = (min_value, max_value)

    async def retrieve_articles(self, session: AsyncSession, schema_id: uuid.UUID, limit: int = 10) -> List[Article]:
        query = select(Article).join(DynamicClassification).where(DynamicClassification.schema_id == schema_id)

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

    async def translate_natural_query(self, query: str, client) -> Dict[str, Any]:
        response = await client.chat.completions.create(
            model="llama3.1" if os.getenv("LOCAL_LLM") == "True" else "gpt-4-0613",
            messages=[
                {"role": "system", "content": "Translate the following natural language query into a structured format for article retrieval."},
                {"role": "user", "content": query},
            ],
            functions=[{
                "name": "construct_query",
                "description": "Construct a query based on the natural language input",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "dimensions": {
                            "type": "object",
                            "description": "Dimensions to query with their weights and ranges"
                        },
                        "filters": {
                            "type": "object",
                            "description": "Filters to apply on the query"
                        }
                    }
                }
            }],
            function_call={"name": "construct_query"}
        )
        return json.loads(response.choices[0].function_call.arguments)

    async def retrieve_articles_from_natural_query(self, session: AsyncSession, query: str, client, limit: int = 10) -> List[Article]:
        structured_query = await self.translate_natural_query(query, client)
        for dimension, params in structured_query['dimensions'].items():
            self.set_dimension_weight(dimension, params['weight'])
            self.set_dimension_range(dimension, params['min'], params['max'])
        # Implement filtering based on structured_query['filters']
        return await self.retrieve_articles(session, limit)

algoquan = AlgoQuan()