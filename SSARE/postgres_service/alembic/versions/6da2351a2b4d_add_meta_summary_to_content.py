"""Add meta_summary to Content

Revision ID: 6da2351a2b4d
Revises: f7678693f47a
Create Date: 2024-11-27 12:12:25.917382

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
import pgvector  
from pgvector.sqlalchemy import Vector



# revision identifiers, used by Alembic.
revision = '6da2351a2b4d'
down_revision = 'f7678693f47a'
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