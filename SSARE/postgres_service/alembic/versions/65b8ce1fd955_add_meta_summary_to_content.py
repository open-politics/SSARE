"""Add meta_summary to Content

Revision ID: 65b8ce1fd955
Revises: 7b2cde544923
Create Date: 2024-11-23 02:14:37.632602

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
import pgvector  
from pgvector.sqlalchemy import Vector



# revision identifiers, used by Alembic.
revision = '65b8ce1fd955'
down_revision = '7b2cde544923'
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