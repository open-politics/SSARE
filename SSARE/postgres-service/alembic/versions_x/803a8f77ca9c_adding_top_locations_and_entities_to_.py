"""Adding top locations and entities to content

Revision ID: 803a8f77ca9c
Revises: f60b0b30e734
Create Date: 2024-12-04 22:49:23.021860

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
import pgvector  
from pgvector.sqlalchemy import Vector



# revision identifiers, used by Alembic.
revision = '803a8f77ca9c'
down_revision = 'f60b0b30e734'
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