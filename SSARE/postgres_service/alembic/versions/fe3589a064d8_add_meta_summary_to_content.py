"""Add meta_summary to Content

Revision ID: fe3589a064d8
Revises: 747f03bedde6
Create Date: 2024-11-26 20:21:37.803849

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
import pgvector  
from pgvector.sqlalchemy import Vector



# revision identifiers, used by Alembic.
revision = 'fe3589a064d8'
down_revision = '747f03bedde6'
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