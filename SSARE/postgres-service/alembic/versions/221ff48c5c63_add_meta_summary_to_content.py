"""Add meta_summary to Content

Revision ID: 221ff48c5c63
Revises: 859e28e9ee42
Create Date: 2024-11-27 00:18:19.614861

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
import pgvector  
from pgvector.sqlalchemy import Vector



# revision identifiers, used by Alembic.
revision = '221ff48c5c63'
down_revision = '859e28e9ee42'
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