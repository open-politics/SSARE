"""Add meta_summary to Content

Revision ID: f45944d63291
Revises: ffd359d93d3a
Create Date: 2024-11-26 17:56:51.438789

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
import pgvector  
from pgvector.sqlalchemy import Vector



# revision identifiers, used by Alembic.
revision = 'f45944d63291'
down_revision = 'ffd359d93d3a'
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