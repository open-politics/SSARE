"""Add meta_summary to Content

Revision ID: aa14a26c9156
Revises: 7d4cbeb2266c
Create Date: 2024-11-18 12:59:17.925964

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
import pgvector  
from pgvector.sqlalchemy import Vector



# revision identifiers, used by Alembic.
revision = 'aa14a26c9156'
down_revision = '7d4cbeb2266c'
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