"""Add meta_summary to Content

Revision ID: 9955f0b63b23
Revises: 2bb8961c5716
Create Date: 2024-11-27 19:20:31.249484

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
import pgvector  
from pgvector.sqlalchemy import Vector



# revision identifiers, used by Alembic.
revision = '9955f0b63b23'
down_revision = '2bb8961c5716'
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