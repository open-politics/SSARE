"""Add meta_summary to Content

Revision ID: 752c2eeb4cb5
Revises: 538edee22df8
Create Date: 2024-11-23 00:37:14.523249

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
import pgvector  
from pgvector.sqlalchemy import Vector



# revision identifiers, used by Alembic.
revision = '752c2eeb4cb5'
down_revision = '538edee22df8'
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