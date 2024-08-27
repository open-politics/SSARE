from typing import Dict, Any, List
from pydantic import create_model, Field
import uuid
from core.classification_schema_manager import schema_manager, ClassificationSchema

class AlgoQual:
    def __init__(self):
        self.schemas: Dict[uuid.UUID, Any] = {}

    def load_schemas(self):
        for schema in schema_manager.get_all_schemas():
            self.schemas[schema.id] = self.create_dynamic_model(schema)

    def create_dynamic_model(self, schema: ClassificationSchema):
        fields = {}
        for field in schema.fields:
            field_type = eval(field.type)
            field_params = {"description": field.description}
            if field.min_value is not None:
                field_params["ge"] = field.min_value
            if field.max_value is not None:
                field_params["le"] = field.max_value
            if field.max_length is not None:
                field_params["max_length"] = field.max_length
            
            fields[field.name] = (field_type, Field(**field_params))

        return create_model(f"Dynamic{schema.name.replace(' ', '')}", **fields)

    def get_llm_prompt(self, schema_id: uuid.UUID) -> str:
        schema = schema_manager.get_schema(schema_id)
        if not schema:
            raise ValueError(f"Schema with id {schema_id} not found")
        field_descriptions = "\n".join([f"- {field.name}: {field.description}" for field in schema.fields])
        return f"{schema.prompt}\n\nPlease provide the following classifications:\n{field_descriptions}"

algoqual = AlgoQual()
algoqual.load_schemas()