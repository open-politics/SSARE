"""Add meta_summary to Content

Revision ID: aafff5bd4bf5
Revises: 1fc62cc8845e
Create Date: 2024-11-26 14:43:45.694184

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
import pgvector  
from pgvector.sqlalchemy import Vector



# revision identifiers, used by Alembic.
revision = 'aafff5bd4bf5'
down_revision = '1fc62cc8845e'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    pass
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    pass
    # ### end Alembic commands ###