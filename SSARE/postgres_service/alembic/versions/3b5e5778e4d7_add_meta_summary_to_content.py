"""Add meta_summary to Content

Revision ID: 3b5e5778e4d7
Revises: 16002f493b13
Create Date: 2024-11-22 23:29:12.501766

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
import pgvector  
from pgvector.sqlalchemy import Vector



# revision identifiers, used by Alembic.
revision = '3b5e5778e4d7'
down_revision = '16002f493b13'
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