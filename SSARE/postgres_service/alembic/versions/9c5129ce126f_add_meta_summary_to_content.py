"""Add meta_summary to Content

Revision ID: 9c5129ce126f
Revises: a1aaca22c6b2
Create Date: 2024-11-23 02:06:31.840662

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
import pgvector  
from pgvector.sqlalchemy import Vector



# revision identifiers, used by Alembic.
revision = '9c5129ce126f'
down_revision = 'a1aaca22c6b2'
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