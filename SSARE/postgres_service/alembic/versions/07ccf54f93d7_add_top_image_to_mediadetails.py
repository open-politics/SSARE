"""Add top_image to MediaDetails

Revision ID: 07ccf54f93d7
Revises: 025d263ae03f
Create Date: 2024-11-18 11:16:36.449561

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
import pgvector  
from pgvector.sqlalchemy import Vector



# revision identifiers, used by Alembic.
revision = '07ccf54f93d7'
down_revision = '025d263ae03f'
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