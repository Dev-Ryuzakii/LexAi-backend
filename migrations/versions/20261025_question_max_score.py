"""Persist each question's maximum score.

Revision ID: 20261025_question_max_score
Revises: 20261015_security_ownership
"""
import sqlalchemy as sa
from alembic import op

revision = '20261025_question_max_score'
down_revision = '20261015_security_ownership'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('questions', sa.Column('max_score', sa.Float(), nullable=False, server_default='5'))


def downgrade():
    op.drop_column('questions', 'max_score')
