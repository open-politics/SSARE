"""Add meta_summary to Content

Revision ID: 1cfcaae58f7e
Revises: 9418f78ae19d
Create Date: 2024-11-18 15:04:48.209847

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
import pgvector  
from pgvector.sqlalchemy import Vector



# revision identifiers, used by Alembic.
revision = '1cfcaae58f7e'
down_revision = '9418f78ae19d'
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