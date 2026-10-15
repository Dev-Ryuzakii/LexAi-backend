"""Ownership, hashed credentials, grading status

Brings the schema in line with src/database.py:
- users.password_hash / users.created_at, auth_tokens table (missing from earlier migrations)
- owner_id on questions, students and responses; matric numbers unique per owner
- one response per (student, question); grading_status, max_score, scoring_method
- API keys stored as SHA-256 digests (key_hash, key_prefix); plaintext column dropped
- existing login tokens were stored in plaintext and are deleted (users log in again)

Set LEGACY_OWNER_EMAIL to assign pre-existing questions/students/responses to that
user; otherwise they have no owner and are not returned by the API.

Revision ID: 20261015_security_ownership
Revises: 20251026_add_users_api_keys
"""
import hashlib
import os

import sqlalchemy as sa
from alembic import op

revision = '20261015_security_ownership'
down_revision = '20251026_add_users_api_keys'
branch_labels = None
depends_on = None

SQLITE_NAMING = {"uq": "uq_%(table_name)s_%(column_0_name)s", "fk": "fk_%(table_name)s_%(column_0_name)s"}


def _columns(insp, table):
    return {c['name'] for c in insp.get_columns(table)}


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    # --- users -----------------------------------------------------------------
    user_cols = _columns(insp, 'users')
    with op.batch_alter_table('users') as batch:
        if 'password_hash' not in user_cols:
            batch.add_column(sa.Column('password_hash', sa.String(255), nullable=True))
        else:
            batch.alter_column('password_hash', type_=sa.String(255), existing_nullable=True, nullable=True)
        if 'created_at' not in user_cols:
            batch.add_column(sa.Column('created_at', sa.DateTime(), nullable=True))

    # --- auth_tokens -------------------------------------------------------------
    if 'auth_tokens' not in tables:
        op.create_table(
            'auth_tokens',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('token', sa.String(128), nullable=False, unique=True),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('expires_at', sa.DateTime(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=True),
        )
    else:
        op.execute('DELETE FROM auth_tokens')

    # --- ownership ----------------------------------------------------------------
    for table in ('questions', 'students', 'responses'):
        if 'owner_id' not in _columns(insp, table):
            with op.batch_alter_table(table, naming_convention=SQLITE_NAMING) as batch:
                batch.add_column(sa.Column('owner_id', sa.Integer(), nullable=True))
                batch.create_foreign_key(f'fk_{table}_owner_id', 'users', ['owner_id'], ['id'])
                batch.create_index(f'ix_{table}_owner_id', ['owner_id'])

    legacy_email = os.environ.get('LEGACY_OWNER_EMAIL')
    if legacy_email:
        owner = bind.execute(sa.text('SELECT id FROM users WHERE email = :e'), {'e': legacy_email.lower()}).first()
        if owner is None:
            raise RuntimeError(f'LEGACY_OWNER_EMAIL {legacy_email} does not match any user')
        for table in ('questions', 'students', 'responses'):
            bind.execute(sa.text(f'UPDATE {table} SET owner_id = :o WHERE owner_id IS NULL'), {'o': owner.id})

    # --- students: matric number unique per owner, fractional totals --------------------
    global_uq = next((uc for uc in insp.get_unique_constraints('students') if uc['column_names'] == ['matric_number']), None)
    with op.batch_alter_table('students', naming_convention=SQLITE_NAMING) as batch:
        if global_uq is not None:
            batch.drop_constraint(global_uq['name'] or 'uq_students_matric_number', type_='unique')
        batch.create_unique_constraint('uq_students_owner_matric', ['owner_id', 'matric_number'])
        batch.alter_column('score', type_=sa.Float(), existing_type=sa.Integer())

    # --- responses ------------------------------------------------------------------
    duplicates = bind.execute(sa.text(
        'SELECT student_id, question_id, COUNT(*) FROM responses GROUP BY student_id, question_id HAVING COUNT(*) > 1'
    )).fetchall()
    if duplicates:
        raise RuntimeError(
            'Cannot add the one-response-per-question constraint: these (student_id, question_id) pairs have '
            f'several responses: {[tuple(d[:2]) for d in duplicates[:20]]}. Remove the extras, then rerun.'
        )
    response_cols = _columns(insp, 'responses')
    with op.batch_alter_table('responses', naming_convention=SQLITE_NAMING) as batch:
        if 'max_score' not in response_cols:
            batch.add_column(sa.Column('max_score', sa.Float(), nullable=True, server_default='5'))
        if 'grading_status' not in response_cols:
            batch.add_column(sa.Column('grading_status', sa.String(20), nullable=False, server_default='graded'))
        if 'scoring_method' not in response_cols:
            batch.add_column(sa.Column('scoring_method', sa.String(50), nullable=True))
        batch.create_unique_constraint('uq_responses_student_question', ['student_id', 'question_id'])

    # --- api_keys: hash existing keys, drop plaintext ---------------------------------------
    key_cols = _columns(insp, 'api_keys')
    with op.batch_alter_table('api_keys') as batch:
        if 'key_hash' not in key_cols:
            batch.add_column(sa.Column('key_hash', sa.String(64), nullable=True))
        if 'key_prefix' not in key_cols:
            batch.add_column(sa.Column('key_prefix', sa.String(20), nullable=True))
        if 'plan_type' not in key_cols:
            batch.add_column(sa.Column('plan_type', sa.String(20), nullable=True))
        if 'created_at' not in key_cols:
            batch.add_column(sa.Column('created_at', sa.DateTime(), nullable=True))

    if 'api_key' in key_cols:
        for row in bind.execute(sa.text('SELECT id, api_key FROM api_keys')).fetchall():
            bind.execute(
                sa.text('UPDATE api_keys SET key_hash = :h, key_prefix = :p WHERE id = :id'),
                {'h': hashlib.sha256(row.api_key.encode()).hexdigest(), 'p': row.api_key[:12], 'id': row.id},
            )

    unique_on_api_key = [uc['name'] for uc in insp.get_unique_constraints('api_keys') if uc['column_names'] == ['api_key']]
    with op.batch_alter_table('api_keys', naming_convention=SQLITE_NAMING) as batch:
        if 'api_key' in key_cols:
            for name in unique_on_api_key:
                batch.drop_constraint(name or 'uq_api_keys_api_key', type_='unique')
            batch.drop_column('api_key')
        batch.alter_column('key_hash', existing_type=sa.String(64), nullable=False)
        batch.alter_column('key_prefix', existing_type=sa.String(20), nullable=False)
        batch.create_unique_constraint('uq_api_keys_key_hash', ['key_hash'])


def downgrade():
    # API keys and tokens are now stored as one-way hashes; the plaintext cannot be restored.
    raise NotImplementedError('Restore from a backup taken before this migration to downgrade.')
