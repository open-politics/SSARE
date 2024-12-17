"""Merge heads

Revision ID: 66469acf788f
Revises: 8b6803be29b7
Create Date: 2024-11-10 21:13:46.023873

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
import pgvector  
from pgvector.sqlalchemy import Vector



# revision identifiers, used by Alembic.
revision = '66469acf788f'
down_revision = '8b6803be29b7'
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass