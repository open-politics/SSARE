"""Adding top locations and entities to content

Revision ID: ce6bff35eb46
Revises: 6e802b81e4c0
Create Date: 2024-12-25 19:47:51.898547

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
import pgvector  
from pgvector.sqlalchemy import Vector



# revision identifiers, used by Alembic.
revision = 'ce6bff35eb46'
down_revision = '6e802b81e4c0'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands to drop embeddings columns ###
    op.drop_column('content', 'embeddings')
    op.drop_column('contentchunk', 'embeddings')
    op.drop_column('image', 'embeddings')
    op.drop_column('videoframe', 'embeddings')
    # ### end Alembic commands ###


def downgrade():
    # ### commands to add embeddings columns back ###
    op.add_column('content', sa.Column('embeddings', pgvector.sqlalchemy.vector.VECTOR(dim=768), nullable=True))
    op.add_column('contentchunk', sa.Column('embeddings', pgvector.sqlalchemy.vector.VECTOR(dim=768), nullable=True))
    op.add_column('image', sa.Column('embeddings', pgvector.sqlalchemy.vector.VECTOR(dim=768), nullable=True))
    op.add_column('videoframe', sa.Column('embeddings', pgvector.sqlalchemy.vector.VECTOR(dim=768), nullable=True))
    # ### end Alembic commands ###