"""Add meta_summary to Content

Revision ID: 9418f78ae19d
Revises: dece8b0885be
Create Date: 2024-11-18 15:04:03.813602

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
import pgvector  
from pgvector.sqlalchemy import Vector



# revision identifiers, used by Alembic.
revision = '9418f78ae19d'
down_revision = 'dece8b0885be'
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