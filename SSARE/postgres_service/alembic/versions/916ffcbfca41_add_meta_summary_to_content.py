"""Add meta_summary to Content

Revision ID: 916ffcbfca41
Revises: f2fab1ee1d08
Create Date: 2024-11-23 01:11:40.140830

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
import pgvector  
from pgvector.sqlalchemy import Vector



# revision identifiers, used by Alembic.
revision = '916ffcbfca41'
down_revision = 'f2fab1ee1d08'
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