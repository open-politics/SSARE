"""Add meta_summary to Content

Revision ID: 7b2cde544923
Revises: 9c5129ce126f
Create Date: 2024-11-23 02:08:56.831809

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
import pgvector  
from pgvector.sqlalchemy import Vector



# revision identifiers, used by Alembic.
revision = '7b2cde544923'
down_revision = '9c5129ce126f'
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