"""Add meta_summary to Content

Revision ID: f616907b0d60
Revises: 6a47d86b6d63
Create Date: 2024-11-26 17:27:38.298033

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
import pgvector  
from pgvector.sqlalchemy import Vector



# revision identifiers, used by Alembic.
revision = 'f616907b0d60'
down_revision = '6a47d86b6d63'
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