"""Add meta_summary to Content

Revision ID: b7ed4814c4c1
Revises: ef06900a5197
Create Date: 2024-11-27 01:15:10.606941

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
import pgvector  
from pgvector.sqlalchemy import Vector



# revision identifiers, used by Alembic.
revision = 'b7ed4814c4c1'
down_revision = 'ef06900a5197'
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