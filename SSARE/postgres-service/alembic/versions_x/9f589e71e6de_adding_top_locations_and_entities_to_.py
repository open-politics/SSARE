"""Adding top locations and entities to content

Revision ID: 9f589e71e6de
Revises: 0d4d3d9cb61b
Create Date: 2024-12-04 19:57:27.337097

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
import pgvector  
from pgvector.sqlalchemy import Vector



# revision identifiers, used by Alembic.
revision = '9f589e71e6de'
down_revision = '0d4d3d9cb61b'
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