"""Add meta_summary to Content

Revision ID: 518296d9f260
Revises: 71838ca0d14e
Create Date: 2024-11-26 15:40:18.439817

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
import pgvector  
from pgvector.sqlalchemy import Vector



# revision identifiers, used by Alembic.
revision = '518296d9f260'
down_revision = '71838ca0d14e'
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