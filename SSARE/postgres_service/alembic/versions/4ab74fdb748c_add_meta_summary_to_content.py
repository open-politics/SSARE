"""Add meta_summary to Content

Revision ID: 4ab74fdb748c
Revises: 98b6a80a7dd1
Create Date: 2024-11-18 12:18:05.240374

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
import pgvector  
from pgvector.sqlalchemy import Vector



# revision identifiers, used by Alembic.
revision = '4ab74fdb748c'
down_revision = '98b6a80a7dd1'
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