"""Add meta_summary to Content

Revision ID: 96a521866537
Revises: e503fd1b1045
Create Date: 2024-11-26 15:48:23.990077

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
import pgvector  
from pgvector.sqlalchemy import Vector



# revision identifiers, used by Alembic.
revision = '96a521866537'
down_revision = 'e503fd1b1045'
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