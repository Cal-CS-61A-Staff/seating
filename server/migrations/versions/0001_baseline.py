"""Baseline: the schema before migrations existed.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-11-18 14:12:26.384671

Databases made before this (staging's, built by `flask initdb` and changed by
hand since) already have some or all of these tables. Upgrading one creates the
tables it is missing, adds the columns its tables are missing, and records this
revision.
"""
from alembic import context, op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0001_baseline'
down_revision = None
branch_labels = None
depends_on = None


# Each table, then its indexes as (column, unique). Index names follow the
# models' ix_<table>_<column>. StringSet columns are Text in the database.
# A function, so each run gets new Column objects: a Column belongs to one table.
def tables():
    return [
        (('offerings',
          sa.Column('id', sa.Integer(), nullable=False),
          sa.Column('canvas_id', sa.String(length=255), nullable=False),
          sa.Column('name', sa.String(length=255), nullable=False),
          sa.Column('code', sa.String(length=255), nullable=False),
          sa.Column('start_at', sa.String(length=255), nullable=False),
          sa.Column('is_hidden', sa.Boolean(), server_default=sa.false(), nullable=False),
          sa.PrimaryKeyConstraint('id')),
         [('canvas_id', True)]),
        (('users',
          sa.Column('id', sa.Integer(), nullable=False),
          sa.Column('name', sa.String(length=255), nullable=False),
          sa.Column('canvas_id', sa.String(length=255), nullable=False),
          sa.Column('staff_offerings', sa.Text(), nullable=False),
          sa.Column('student_offerings', sa.Text(), nullable=False),
          sa.PrimaryKeyConstraint('id')),
         [('canvas_id', True), ('name', False)]),
        (('canvas_tokens',
          sa.Column('id', sa.Integer(), nullable=False),
          sa.Column('user_id', sa.Integer(), nullable=False),
          sa.Column('handle_hash', sa.String(length=64), nullable=False),
          sa.Column('access_token', sa.Text(), nullable=False),
          sa.Column('expires_at', sa.Integer(), nullable=False),
          sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
          sa.PrimaryKeyConstraint('id')),
         [('handle_hash', True), ('user_id', False)]),
        (('exams',
          sa.Column('id', sa.Integer(), nullable=False),
          sa.Column('offering_canvas_id', sa.String(length=255), nullable=False),
          sa.Column('name', sa.String(length=255), nullable=False),
          sa.Column('display_name', sa.String(length=255), nullable=False),
          sa.Column('is_active', sa.BOOLEAN(), nullable=False),
          sa.ForeignKeyConstraint(['offering_canvas_id'], ['offerings.canvas_id'], ondelete='CASCADE'),
          sa.PrimaryKeyConstraint('id'),
          sa.UniqueConstraint('offering_canvas_id', 'name', name='uq_offering_canvas_id_name')),
         [('name', False), ('offering_canvas_id', False)]),
        (('rooms',
          sa.Column('id', sa.Integer(), nullable=False),
          sa.Column('exam_id', sa.Integer(), nullable=False),
          sa.Column('name', sa.String(length=255), nullable=False),
          sa.Column('display_name', sa.String(length=255), nullable=False),
          sa.Column('start_at', sa.String(length=255), nullable=True),
          sa.Column('duration_minutes', sa.Integer(), nullable=True),
          sa.ForeignKeyConstraint(['exam_id'], ['exams.id'], ondelete='CASCADE'),
          sa.PrimaryKeyConstraint('id'),
          sa.UniqueConstraint('exam_id', 'name', 'start_at', name='uq_exam_id_name_start_at')),
         [('exam_id', False), ('name', False)]),
        (('students',
          sa.Column('id', sa.Integer(), nullable=False),
          sa.Column('exam_id', sa.Integer(), nullable=False),
          sa.Column('canvas_id', sa.String(length=255), nullable=False),
          sa.Column('email', sa.String(length=255), nullable=False),
          sa.Column('name', sa.String(length=255), nullable=False),
          sa.Column('sid', sa.String(length=255), nullable=True),
          sa.Column('canvas_sid', sa.String(length=255), nullable=True),
          sa.Column('wants', sa.Text(), nullable=False),
          sa.Column('avoids', sa.Text(), nullable=False),
          sa.Column('room_wants', sa.Text(), nullable=False),
          sa.Column('room_avoids', sa.Text(), nullable=False),
          sa.ForeignKeyConstraint(['exam_id'], ['exams.id'], ondelete='CASCADE'),
          sa.PrimaryKeyConstraint('id')),
         [('canvas_id', False), ('email', False), ('exam_id', False)]),
        (('seats',
          sa.Column('id', sa.Integer(), nullable=False),
          sa.Column('room_id', sa.Integer(), nullable=False),
          sa.Column('fixed', sa.Boolean(), nullable=False),
          sa.Column('name', sa.String(length=255), nullable=True),
          sa.Column('row', sa.String(length=255), nullable=True),
          sa.Column('seat', sa.String(length=255), nullable=True),
          sa.Column('x', sa.Float(), nullable=True),
          sa.Column('y', sa.Float(), nullable=True),
          sa.Column('attributes', sa.Text(), nullable=False),
          sa.ForeignKeyConstraint(['room_id'], ['rooms.id'], ondelete='CASCADE'),
          sa.PrimaryKeyConstraint('id')),
         [('room_id', False), ('seat', False)]),
        (('seat_assignments',
          sa.Column('student_id', sa.Integer(), nullable=False),
          sa.Column('seat_id', sa.Integer(), nullable=False),
          sa.Column('emailed', sa.Boolean(), nullable=False),
          sa.ForeignKeyConstraint(['seat_id'], ['seats.id'], ondelete='CASCADE'),
          sa.ForeignKeyConstraint(['student_id'], ['students.id'], ondelete='CASCADE'),
          sa.PrimaryKeyConstraint('student_id', 'seat_id')),
         [('emailed', False), ('seat_id', False), ('student_id', False)]),
    ]


def upgrade():
    if context.is_offline_mode():
        # `flask db upgrade --sql` has no database to look at: write the SQL for all of it
        inspector, existing = None, set()
    else:
        inspector = sa.inspect(op.get_bind())
        existing = set(inspector.get_table_names())
    for (name, *items), indexes in tables():
        if name not in existing:
            op.create_table(name, *items)
            for column, unique in indexes:
                op.create_index(f'ix_{name}_{column}', name, [column], unique=unique)
            continue
        # Columns added to the models after this database was made, such as offerings.is_hidden
        # and students.canvas_sid. Each was nullable or had a default, so it can be added here.
        have = {column['name'] for column in inspector.get_columns(name)}
        for column in items:
            if isinstance(column, sa.Column) and column.name not in have:
                if not column.nullable and column.server_default is None:
                    raise RuntimeError(f'{name}.{column.name} is missing, and is required with no default: '
                                       f'add it by hand, then upgrade again')
                op.add_column(name, column)


def downgrade():
    for (name, *_), _indexes in reversed(tables()):
        op.drop_table(name)
