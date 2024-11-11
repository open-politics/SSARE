"""Merge heads

Revision ID: 05612c979b4f
Revises: c9399d4ec65e
Create Date: 2024-11-10 21:11:38.963989

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
import pgvector  
from pgvector.sqlalchemy import Vector



# revision identifiers, used by Alembic.
revision = '05612c979b4f'
down_revision = 'c9399d4ec65e'
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass