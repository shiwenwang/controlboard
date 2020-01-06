'''
@Descripttion: 
@version: 
@Author: wangshiwen@36719
@Date: 2020-01-05 16:32:26
@LastEditors  : wangshiwen@36719
@LastEditTime : 2020-01-05 16:35:15
'''
"""empty message

Revision ID: a8ede3253fdf
Revises: 9c88c0bc500f
Create Date: 2020-01-05 16:32:26.722520

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a8ede3253fdf'
down_revision = '9c88c0bc500f'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('task', sa.Column('mode_damps', sa.String(length=256), nullable=True))
    op.add_column('task', sa.Column('mode_freqs', sa.String(length=256), nullable=True))
    op.add_column('task', sa.Column('mode_names', sa.String(length=256), nullable=True))
    with op.batch_alter_table('task') as batch_op:
        batch_op.drop_column('tower_mode_1')
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('task', sa.Column('tower_mode_1', sa.FLOAT(), nullable=True))
    op.drop_column('task', 'mode_names')
    op.drop_column('task', 'mode_freqs')
    op.drop_column('task', 'mode_damps')
    # ### end Alembic commands ###