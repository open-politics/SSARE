"""Add meta_summary to Content

Revision ID: 1a12f2543524
Revises: 504ab7c7f378
Create Date: 2024-11-18 20:10:05.676967

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
import pgvector  
from pgvector.sqlalchemy import Vector



# revision identifiers, used by Alembic.
revision = '1a12f2543524'
down_revision = '504ab7c7f378'
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