"""Usage analytics, webhooks, IP rules, jobs, idempotency keys

Revision ID: 20261016_platform_features
Revises: 20261015_security_ownership
"""
import sqlalchemy as sa
from alembic import op

revision = '20261016_platform_features'
down_revision = '20261015_security_ownership'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'api_usage',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('api_key_id', sa.Integer(), sa.ForeignKey('api_keys.id'), nullable=True),
        sa.Column('method', sa.String(10), nullable=False),
        sa.Column('endpoint', sa.String(200), nullable=False),
        sa.Column('status_code', sa.Integer(), nullable=False),
        sa.Column('response_time', sa.Float(), nullable=False),
        sa.Column('request_size', sa.Integer(), nullable=True),
        sa.Column('response_size', sa.Integer(), nullable=True),
        sa.Column('units', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_api_usage_user_created', 'api_usage', ['user_id', 'created_at'])
    op.create_index('ix_api_usage_api_key_id', 'api_usage', ['api_key_id'])

    op.create_table(
        'api_key_ip_rules',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('api_key_id', sa.Integer(), sa.ForeignKey('api_keys.id', ondelete='CASCADE'), nullable=False),
        sa.Column('ip_address', sa.String(64), nullable=False),
        sa.Column('is_whitelist', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_api_key_ip_rules_api_key_id', 'api_key_ip_rules', ['api_key_id'])

    op.create_table(
        'webhooks',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('url', sa.String(2000), nullable=False),
        sa.Column('events', sa.Text(), nullable=False),
        sa.Column('secret', sa.String(100), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('last_delivery_at', sa.DateTime(), nullable=True),
        sa.Column('last_status', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_webhooks_user_id', 'webhooks', ['user_id'])

    op.create_table(
        'jobs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('type', sa.String(50), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('result', sa.Text(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('ended_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_jobs_user_id', 'jobs', ['user_id'])

    op.create_table(
        'idempotency_keys',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('key', sa.String(100), nullable=False),
        sa.Column('fingerprint', sa.String(64), nullable=False),
        sa.Column('status_code', sa.Integer(), nullable=True),
        sa.Column('response_body', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('user_id', 'key', name='uq_idempotency_user_key'),
    )
    op.create_index('ix_idempotency_keys_created_at', 'idempotency_keys', ['created_at'])


def downgrade():
    for table in ('idempotency_keys', 'jobs', 'webhooks', 'api_key_ip_rules', 'api_usage'):
        op.drop_table(table)
