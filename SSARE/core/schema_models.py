from typing import List, Optional
from sqlmodel import Field, SQLModel, Relationship
import uuid

class ClassificationField(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    schema_id: uuid.UUID = Field(foreign_key="classificationschema.id")
    name: str
    type: str
    description: str
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    max_length: Optional[int] = None
    max_items: Optional[int] = None

    schema: "ClassificationSchema" = Relationship(back_populates="fields")

class ClassificationSchema(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(index=True)
    prompt: str
    fields: List[ClassificationField] = Relationship(back_populates="schema")

    classifications: List["DynamicClassification"] = Relationship(back_populates="schema")