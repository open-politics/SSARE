"""Add meta_summary to Content

Revision ID: a1aaca22c6b2
Revises: af3158e711f1
Create Date: 2024-11-23 02:04:26.341034

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
import pgvector  
from pgvector.sqlalchemy import Vector



# revision identifiers, used by Alembic.
revision = 'a1aaca22c6b2'
down_revision = 'af3158e711f1'
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