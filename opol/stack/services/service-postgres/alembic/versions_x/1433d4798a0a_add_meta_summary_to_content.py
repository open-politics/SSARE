"""Add meta_summary to Content

Revision ID: 1433d4798a0a
Revises: d7ebac17a5eb
Create Date: 2024-11-19 19:04:13.122270

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
import pgvector  
from pgvector.sqlalchemy import Vector



# revision identifiers, used by Alembic.
revision = '1433d4798a0a'
down_revision = 'd7ebac17a5eb'
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