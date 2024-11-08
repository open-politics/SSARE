"""Autogenerated migration

Revision ID: 2a319621f6b2
Revises: 
Create Date: 2024-11-05 13:09:42.568118

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
import pgvector  



# revision identifiers, used by Alembic.
revision = '2a319621f6b2'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index('ix_classificationdimension_name', table_name='classificationdimension')
    op.create_index(op.f('ix_classificationdimension_name'), 'classificationdimension', ['name'], unique=True)
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_classificationdimension_name'), table_name='classificationdimension')
    op.create_index('ix_classificationdimension_name', 'classificationdimension', ['name'], unique=False)
    # ### end Alembic commands ###