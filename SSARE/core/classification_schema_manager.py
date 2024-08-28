import csv
import os
from typing import List, Optional
import uuid
import logging
from core.schema_models import ClassificationSchema, ClassificationField

class ClassificationSchemaManager:
    def __init__(self, schema_file: str = '/app/core/classification_schemas.csv'):
        self.schema_file = schema_file
        self.schemas: List[ClassificationSchema] = []
        logging.error(f"Schema file path: {self.schema_file}")
        logging.error(f"Schema file content: {self.schema_file}")

    def load_schemas(self):
        if not os.path.exists(self.schema_file):
            logging.error(f"Schema file not found: {self.schema_file}")
            return

        with open(self.schema_file, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            logging.info(f"Found {len(rows)} rows in CSV file")
            
            current_schema = None
            for row in rows:
                if row['schema_name']:
                    if current_schema:
                        self.schemas.append(current_schema)
                    current_schema = ClassificationSchema(
                        id=uuid.uuid4(),
                        name=row['schema_name'],
                        prompt=row['prompt'],
                        fields=[]
                    )
                if current_schema:  # Only add field if there's a current schema
                    field = ClassificationField(
                        id=uuid.uuid4(),
                        name=row['field_name'],
                        type=row['field_type'],
                        description=row['description'],
                        min_value=float(row['min_value']) if row['min_value'] else None,
                        max_value=float(row['max_value']) if row['max_value'] else None,
                        max_length=int(row['max_length']) if row['max_length'] else None,
                        max_items=int(row['max_items']) if row['max_items'] else None
                    )
                    current_schema.fields.append(field)
            if current_schema:
                self.schemas.append(current_schema)
        
        logging.info(f"Loaded {len(self.schemas)} schemas from CSV")

    def get_schema(self, schema_id: uuid.UUID) -> Optional[ClassificationSchema]:
        return next((schema for schema in self.schemas if schema.id == schema_id), None)

    def get_schema_by_name(self, name: str) -> Optional[ClassificationSchema]:
        return next((schema for schema in self.schemas if schema.name == name), None)

    def get_all_schemas(self) -> List[ClassificationSchema]:
        return self.schemas

schema_manager = ClassificationSchemaManager()
schema_manager.load_schemas()