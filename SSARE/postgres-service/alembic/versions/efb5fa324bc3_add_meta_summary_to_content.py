"""Add meta_summary to Content

Revision ID: efb5fa324bc3
Revises: 518296d9f260
Create Date: 2024-11-26 15:40:39.277503

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
import pgvector  
from pgvector.sqlalchemy import Vector



# revision identifiers, used by Alembic.
revision = 'efb5fa324bc3'
down_revision = '518296d9f260'
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