"""Add meta_summary to Content

Revision ID: 69c12aa779b5
Revises: 4081b1d6c18c
Create Date: 2024-11-18 19:45:38.513888

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
import pgvector  
from pgvector.sqlalchemy import Vector



# revision identifiers, used by Alembic.
revision = '69c12aa779b5'
down_revision = '4081b1d6c18c'
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