"""Nullable FeatureLayerBase attributes in Layer

Revision ID: ef3e2aad073d
Revises: d903c3d3ec87
Create Date: 2023-07-10 13:29:39.523316

"""
from alembic import op
import sqlalchemy as sa
import geoalchemy2
import sqlmodel  



# revision identifiers, used by Alembic.
revision = 'ef3e2aad073d'
down_revision = 'd903c3d3ec87'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('layer', 'feature_layer_type',
               existing_type=sa.TEXT(),
               nullable=True,
               schema='customer')
    op.alter_column('layer', 'size',
               existing_type=sa.INTEGER(),
               nullable=True,
               schema='customer')
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('layer', 'size',
               existing_type=sa.INTEGER(),
               nullable=False,
               schema='customer')
    op.alter_column('layer', 'feature_layer_type',
               existing_type=sa.TEXT(),
               nullable=False,
               schema='customer')
    # ### end Alembic commands ###
