"""Merge heads

Revision ID: f20f89e7e5a3
Revises: de882a610024
Create Date: 2024-11-10 21:12:53.170987

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
import pgvector  
from pgvector.sqlalchemy import Vector



# revision identifiers, used by Alembic.
revision = 'f20f89e7e5a3'
down_revision = 'de882a610024'
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass