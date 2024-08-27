import csv
from typing import List, Optional
from pydantic import BaseModel, Field
import uuid

class ClassificationField(BaseModel):
    name: str
    type: str
    description: str
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    max_length: Optional[int] = None
    max_items: Optional[int] = None

class ClassificationSchema(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    name: str
    prompt: str
    fields: List[ClassificationField]

class ClassificationSchemaManager:
    def __init__(self, schema_file: str = 'core/schemas.csv'):
        self.schema_file = schema_file
        self.schemas: List[ClassificationSchema] = []
        self.load_schemas()

    def load_schemas(self):
        with open(self.schema_file, 'r') as f:
            reader = csv.DictReader(f)
            current_schema = None
            for row in reader:
                if row['schema_name']:
                    if current_schema:
                        self.schemas.append(ClassificationSchema(**current_schema))
                    current_schema = {
                        'name': row['schema_name'],
                        'prompt': row['prompt'],
                        'fields': []
                    }
                field = ClassificationField(
                    name=row['field_name'],
                    type=row['field_type'],
                    description=row['description'],
                    min_value=float(row['min_value']) if row['min_value'] else None,
                    max_value=float(row['max_value']) if row['max_value'] else None,
                    max_length=int(row['max_length']) if row['max_length'] else None,
                    max_items=int(row['max_items']) if row['max_items'] else None
                )
                current_schema['fields'].append(field)
            if current_schema:
                self.schemas.append(ClassificationSchema(**current_schema))

    def get_schema(self, schema_id: uuid.UUID) -> Optional[ClassificationSchema]:
        return next((schema for schema in self.schemas if schema.id == schema_id), None)

    def get_schema_by_name(self, name: str) -> Optional[ClassificationSchema]:
        return next((schema for schema in self.schemas if schema.name == name), None)

    def get_all_schemas(self) -> List[ClassificationSchema]:
        return self.schemas

schema_manager = ClassificationSchemaManager()